# auth.tf — Amazon Cognito (autenticación del panel de administración)
# Los editores se autentican contra este User Pool. Cognito emite un JWT que
# API Gateway valida de forma nativa antes de permitir operaciones de escritura.

resource "aws_cognito_user_pool" "editors" {
  name = "${local.name_prefix}-editors"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}

resource "aws_cognito_user_pool_client" "admin_app" {
  name         = "${local.name_prefix}-admin-client"
  user_pool_id = aws_cognito_user_pool.editors.id

  generate_secret = false # SPA pública: sin client secret

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["email", "openid", "profile"]
  supported_identity_providers         = ["COGNITO"]

  callback_urls = ["https://${aws_cloudfront_distribution.admin_web.domain_name}"]
  logout_urls   = ["https://${aws_cloudfront_distribution.admin_web.domain_name}"]
}

# Dominio para la Hosted UI de login que ofrece Cognito lista para usar.
resource "aws_cognito_user_pool_domain" "this" {
  domain       = "${local.name_prefix}-auth-${local.suffix}"
  user_pool_id = aws_cognito_user_pool.editors.id
}
