# ai.tf — Capa de IA: Lambdas de resumen + SQS/DLQ + EventBridge + Bedrock

# empaqueta la carpeta ai/ en un zip; lo comparten las dos Lambdas
data "archive_file" "ai_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../ai"
  output_path = "${path.module}/build/ai_lambda.zip"
}

# Cola de reintentos (Dead Letter Queue) para resiliencia
resource "aws_sqs_queue" "summarize_dlq" {
  name                      = "${local.name_prefix}-summarize-dlq"
  message_retention_seconds = 1209600 # 14 días
}

# DLQ del resumen diario (si el Scheduler no logra invocar la Lambda).
resource "aws_sqs_queue" "daily_dlq" {
  name                      = "${local.name_prefix}-daily-dlq"
  message_retention_seconds = 1209600
}

# Rol compartido de las Lambdas de IA (DynamoDB + Streams + Bedrock + logs)
resource "aws_iam_role" "ai_lambda" {
  name               = "${local.name_prefix}-ai-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "ai_lambda_logs" {
  role       = aws_iam_role.ai_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "ai_lambda" {
  # Lectura/escritura de artículos y resúmenes.
  statement {
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [
      aws_dynamodb_table.content.arn,
      "${aws_dynamodb_table.content.arn}/index/*",
    ]
  }

  # Consumo del stream de DynamoDB.
  statement {
    actions = [
      "dynamodb:GetRecords",
      "dynamodb:GetShardIterator",
      "dynamodb:DescribeStream",
      "dynamodb:ListStreams",
    ]
    resources = [aws_dynamodb_table.content.stream_arn]
  }

  # Invocación de modelos de Bedrock.
  statement {
    actions   = ["bedrock:InvokeModel"]
    resources = ["*"] # enunciado: abierto. En prod lo ataría al ARN del modelo concreto.
  }

  # Envío a la DLQ.
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.summarize_dlq.arn]
  }
}

resource "aws_iam_role_policy" "ai_lambda" {
  name   = "${local.name_prefix}-ai-policy"
  role   = aws_iam_role.ai_lambda.id
  policy = data.aws_iam_policy_document.ai_lambda.json
}

resource "aws_cloudwatch_log_group" "summarize" {
  name              = "/aws/lambda/${local.name_prefix}-summarize-article"
  retention_in_days = 14
}

# Lambda: resumen de un artículo (disparada por DynamoDB Streams)
resource "aws_lambda_function" "summarize" {
  function_name    = "${local.name_prefix}-summarize-article"
  role             = aws_iam_role.ai_lambda.arn
  handler          = "summarize_article.lambda_handler"
  runtime          = var.lambda_runtime
  architectures    = ["arm64"]
  filename         = data.archive_file.ai_lambda.output_path
  source_code_hash = data.archive_file.ai_lambda.output_base64sha256
  timeout          = 60
  memory_size      = 512
  depends_on       = [aws_cloudwatch_log_group.summarize]

  # Tope de concurrencia: ante un pico de publicación, evita abrir cientos de
  # llamadas simultáneas a Bedrock (throttling) y protege su cuota de la cuenta.
  reserved_concurrent_executions = var.summarize_reserved_concurrency

  environment {
    variables = {
      TABLE_NAME         = aws_dynamodb_table.content.name
      BEDROCK_MODEL_ID   = var.bedrock_model_id
      NEWSNOW_ALLOW_MOCK = "false" # prod: nunca enmascarar un fallo de Bedrock con el mock
    }
  }
}

# Trigger event-driven: cada cambio en la tabla dispara el resumen.
resource "aws_lambda_event_source_mapping" "streams_to_summarize" {
  event_source_arn                   = aws_dynamodb_table.content.stream_arn
  function_name                      = aws_lambda_function.summarize.arn
  starting_position                  = "LATEST"
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5

  # Fallo parcial: si un registro peta, se reintenta solo ese, no el batch entero.
  function_response_types = ["ReportBatchItemFailures"]

  # Reintentos y descarte a la DLQ ante fallos persistentes.
  maximum_retry_attempts = 3
  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.summarize_dlq.arn
    }
  }

  # Solo invoca la Lambda para BORRADORES de artículo (SK=META, status=DRAFT). Así
  # el MODIFY que genera marcar READY no vuelve a disparar el resumen (evita el
  # bucle) ni gastamos invocaciones en las filas de resumen (SK=SUMMARY).
  filter_criteria {
    filter {
      pattern = jsonencode({
        dynamodb = {
          Keys = {
            SK = { S = ["META"] }
          }
          NewImage = {
            status = { S = ["DRAFT"] }
          }
        }
      })
    }
  }
}

resource "aws_cloudwatch_log_group" "daily_summary" {
  name              = "/aws/lambda/${local.name_prefix}-daily-summary"
  retention_in_days = 14
}

# Lambda: resumen diario (disparada por EventBridge Scheduler)
resource "aws_lambda_function" "daily_summary" {
  function_name    = "${local.name_prefix}-daily-summary"
  role             = aws_iam_role.ai_lambda.arn
  handler          = "daily_summary.lambda_handler"
  runtime          = var.lambda_runtime
  architectures    = ["arm64"]
  filename         = data.archive_file.ai_lambda.output_path
  source_code_hash = data.archive_file.ai_lambda.output_base64sha256
  timeout          = 120
  memory_size      = 512
  depends_on       = [aws_cloudwatch_log_group.daily_summary]

  environment {
    variables = {
      TABLE_NAME         = aws_dynamodb_table.content.name
      BEDROCK_MODEL_ID   = var.bedrock_model_id
      NEWSNOW_ALLOW_MOCK = "false" # prod: nunca enmascarar un fallo de Bedrock con el mock
      GSI_SHARDS         = tostring(var.gsi_shards)
    }
  }
}

resource "aws_scheduler_schedule" "daily_summary" {
  name = "${local.name_prefix}-daily-summary"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.daily_summary_cron
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.daily_summary.arn
    role_arn = aws_iam_role.scheduler.arn

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 3
    }
    dead_letter_config {
      arn = aws_sqs_queue.daily_dlq.arn
    }
  }
}

# Rol que permite a EventBridge Scheduler invocar la Lambda.
resource "aws_iam_role" "scheduler" {
  name = "${local.name_prefix}-scheduler-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler_invoke" {
  name = "${local.name_prefix}-scheduler-invoke"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = "lambda:InvokeFunction"
        Effect   = "Allow"
        Resource = aws_lambda_function.daily_summary.arn
      },
      {
        Action   = "sqs:SendMessage"
        Effect   = "Allow"
        Resource = aws_sqs_queue.daily_dlq.arn
      },
    ]
  })
}
