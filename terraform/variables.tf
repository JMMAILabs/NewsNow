# variables.tf — Parámetros de entrada

variable "aws_region" {
  description = "Región principal de AWS donde se despliega la infraestructura."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Nombre del proyecto, usado como prefijo de los recursos."
  type        = string
  default     = "newsnow"
}

variable "environment" {
  description = "Entorno de despliegue (dev / staging / prod)."
  type        = string
  default     = "dev"
}

variable "bedrock_model_id" {
  description = "ID del modelo de Amazon Bedrock para los resúmenes."
  type        = string
  # Claude Haiku 4.5: rápido y económico, ideal para resúmenes de gran volumen.
  # Nota: en algunas regiones (p. ej. eu-west-1) los modelos nuevos requieren un
  # perfil de inferencia cross-region, p. ej. "eu.anthropic.claude-haiku-4-5-20251001-v1:0".
  default = "anthropic.claude-haiku-4-5"
}

variable "daily_summary_cron" {
  description = "Expresión cron (UTC) para el resumen diario de EventBridge."
  type        = string
  default     = "cron(0 6 * * ? *)" # 06:00 UTC cada día
}

variable "lambda_runtime" {
  description = "Runtime de Python para las funciones Lambda."
  type        = string
  default     = "python3.12"
}

variable "summarize_reserved_concurrency" {
  description = "Concurrencia reservada de la Lambda de resumen (tope de llamadas simultáneas a Bedrock ante picos)."
  type        = number
  default     = 10
}

variable "alarms_email" {
  description = "Email para las alarmas de CloudWatch (vacío = sin suscripción; el topic SNS se crea igual)."
  type        = string
  default     = ""
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  suffix      = random_id.suffix.hex
}
