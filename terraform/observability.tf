# observability.tf — Alarmas de CloudWatch + notificación (SNS)
# Cierra el bucle de resiliencia: si algo se rompe (Lambda con errores, eventos
# atascados en la DLQ, 5xx del API) salta una alarma y se notifica por SNS.

resource "aws_sns_topic" "alerts" {
  name = "${local.name_prefix}-alerts"
}

# Suscripción por email opcional (solo si se define var.alarms_email).
resource "aws_sns_topic_subscription" "alerts_email" {
  count     = var.alarms_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarms_email
}

# --- Errores en la Lambda de resumen (p. ej. throttling de Bedrock) ----------
resource "aws_cloudwatch_metric_alarm" "summarize_errors" {
  alarm_name          = "${local.name_prefix}-summarize-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "La Lambda de resumen está fallando (revisar Bedrock/DLQ)."
  dimensions          = { FunctionName = aws_lambda_function.summarize.function_name }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

# --- Eventos atascados en la DLQ del resumen ---------------------------------
resource "aws_cloudwatch_metric_alarm" "summarize_dlq_depth" {
  alarm_name          = "${local.name_prefix}-summarize-dlq-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "Hay eventos en la DLQ: resúmenes que no se pudieron generar."
  dimensions          = { QueueName = aws_sqs_queue.summarize_dlq.name }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

# --- Backlog del stream: el consumo se está quedando atrás --------------------
# Con concurrencia reservada, un pico sostenido de publicación puede encolar más
# rápido de lo que procesamos. Si el IteratorAge crece, hay que subir el tope de
# concurrencia (o revisar Bedrock) antes de acercarnos a la retención del stream.
resource "aws_cloudwatch_metric_alarm" "summarize_iterator_age" {
  alarm_name          = "${local.name_prefix}-summarize-iterator-age"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "IteratorAge"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Maximum"
  threshold           = 600000 # 10 min de retraso en el stream
  alarm_description   = "El consumo del stream se retrasa (backlog): subir concurrencia reservada."
  dimensions          = { FunctionName = aws_lambda_function.summarize.function_name }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

# --- Throttling de la Lambda de resumen (techo de concurrencia reservada) -----
resource "aws_cloudwatch_metric_alarm" "summarize_throttles" {
  alarm_name          = "${local.name_prefix}-summarize-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "La Lambda de resumen se throttlea contra su concurrencia reservada."
  dimensions          = { FunctionName = aws_lambda_function.summarize.function_name }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}

# --- Errores 5xx del API -----------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.name_prefix}-api-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "5xx"
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "El API HTTP está devolviendo errores 5xx."
  dimensions          = { ApiId = aws_apigatewayv2_api.http.id }
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"
}
