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
