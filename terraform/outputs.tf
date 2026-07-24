# outputs.tf — Valores útiles tras el despliegue

output "public_web_url" {
  description = "URL de la web pública (CloudFront)."
  value       = "https://${aws_cloudfront_distribution.public_web.domain_name}"
}

output "admin_web_url" {
  description = "URL del panel de administración (CloudFront)."
  value       = "https://${aws_cloudfront_distribution.admin_web.domain_name}"
}

output "api_endpoint" {
  description = "Endpoint base del API REST."
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "cognito_user_pool_id" {
  description = "ID del User Pool de Cognito."
  value       = aws_cognito_user_pool.editors.id
}

output "cognito_app_client_id" {
  description = "ID del App Client de Cognito para el panel admin."
  value       = aws_cognito_user_pool_client.admin_app.id
}

output "cognito_hosted_ui_domain" {
  description = "Dominio de la Hosted UI de login de Cognito."
  value       = "${aws_cognito_user_pool_domain.this.domain}.auth.${var.aws_region}.amazoncognito.com"
}

output "dynamodb_table_name" {
  description = "Nombre de la tabla DynamoDB."
  value       = aws_dynamodb_table.content.name
}

output "media_bucket" {
  description = "Bucket S3 de media/imágenes."
  value       = aws_s3_bucket.media.bucket
}

output "s3_buckets_to_deploy_frontend" {
  description = "Buckets donde subir el build de cada app React."
  value = {
    public_web = aws_s3_bucket.public_web.bucket
    admin_web  = aws_s3_bucket.admin_web.bucket
  }
}
