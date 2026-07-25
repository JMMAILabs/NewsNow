# api.tf — Backend REST: API Gateway (HTTP API) + Lambda (Python)

# empaqueta la carpeta backend/ en un zip
data "archive_file" "api_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../backend"
  output_path = "${path.module}/build/api_lambda.zip"
}

# Rol de ejecución de la Lambda del backend
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api_lambda" {
  name               = "${local.name_prefix}-api-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Logs en CloudWatch.
resource "aws_iam_role_policy_attachment" "api_lambda_logs" {
  role       = aws_iam_role.api_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Acceso CRUD a la tabla DynamoDB (+ su GSI).
data "aws_iam_policy_document" "api_lambda_ddb" {
  statement {
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
    ]
    resources = [
      aws_dynamodb_table.content.arn,
      "${aws_dynamodb_table.content.arn}/index/*",
    ]
  }
}

resource "aws_iam_role_policy" "api_lambda_ddb" {
  name   = "${local.name_prefix}-api-ddb"
  role   = aws_iam_role.api_lambda.id
  policy = data.aws_iam_policy_document.api_lambda_ddb.json
}

# Log group con retención (por defecto los logs de Lambda no expiran nunca → coste).
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.name_prefix}-api"
  retention_in_days = 14
}

# Lambda del backend
resource "aws_lambda_function" "api" {
  function_name    = "${local.name_prefix}-api"
  role             = aws_iam_role.api_lambda.arn
  handler          = "handler.lambda_handler"
  runtime          = var.lambda_runtime
  architectures    = ["arm64"] # Graviton: ~20% más barato
  filename         = data.archive_file.api_lambda.output_path
  source_code_hash = data.archive_file.api_lambda.output_base64sha256
  timeout          = 15
  memory_size      = 256
  depends_on       = [aws_cloudwatch_log_group.api]

  environment {
    variables = {
      TABLE_NAME   = aws_dynamodb_table.content.name
      MEDIA_BUCKET = aws_s3_bucket.media.bucket
    }
  }
}

# API Gateway HTTP API
resource "aws_apigatewayv2_api" "http" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"] # redes abiertas (según enunciado)
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["*"]
  }
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

# --- Authorizer JWT con Cognito (protege las rutas de escritura) -------------
resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.http.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "${local.name_prefix}-cognito-authorizer"

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.admin_app.id]
    issuer   = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.editors.id}"
  }
}

# --- Rutas públicas (lectura, sin auth) --------------------------------------
resource "aws_apigatewayv2_route" "get_articles" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "GET /articles"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_route" "get_article" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "GET /articles/{id}"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_route" "get_daily" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "GET /daily-summary"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

# --- Rutas de escritura (protegidas con JWT de Cognito) ----------------------
resource "aws_apigatewayv2_route" "create_article" {
  api_id             = aws_apigatewayv2_api.http.id
  route_key          = "POST /articles"
  target             = "integrations/${aws_apigatewayv2_integration.api.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "update_article" {
  api_id             = aws_apigatewayv2_api.http.id
  route_key          = "PUT /articles/{id}"
  target             = "integrations/${aws_apigatewayv2_integration.api.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

resource "aws_apigatewayv2_route" "delete_article" {
  api_id             = aws_apigatewayv2_api.http.id
  route_key          = "DELETE /articles/{id}"
  target             = "integrations/${aws_apigatewayv2_integration.api.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

# Log group para los access logs del API (observabilidad + trazas de errores).
resource "aws_cloudwatch_log_group" "api_gw" {
  name              = "/aws/apigateway/${local.name_prefix}"
  retention_in_days = 14
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gw.arn
    # $context.* son variables de API Gateway (no interpolación de Terraform).
    format = jsonencode({
      requestId       = "$context.requestId"
      ip              = "$context.identity.sourceIp"
      requestTime     = "$context.requestTime"
      httpMethod      = "$context.httpMethod"
      routeKey        = "$context.routeKey"
      status          = "$context.status"
      responseLatency = "$context.responseLatency"
    })
  }

  default_route_settings {
    throttling_burst_limit = 5000
    throttling_rate_limit  = 10000
  }
}

# Permiso para que API Gateway invoque la Lambda.
resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
