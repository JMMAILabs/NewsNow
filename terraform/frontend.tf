# frontend.tf — Hosting estático de las 2 apps React + media (S3 + CloudFront)
# Patrón: bucket S3 privado servido a través de CloudFront con Origin Access
# Control (OAC). El CDN cachea en el edge y absorbe los picos de tráfico.

# Buckets S3
resource "aws_s3_bucket" "public_web" {
  bucket = "${local.name_prefix}-public-web-${local.suffix}"
}

resource "aws_s3_bucket" "admin_web" {
  bucket = "${local.name_prefix}-admin-web-${local.suffix}"
}

resource "aws_s3_bucket" "media" {
  bucket = "${local.name_prefix}-media-${local.suffix}"
}

# Versionado (permite rollback de despliegues del frontend).
resource "aws_s3_bucket_versioning" "public_web" {
  bucket = aws_s3_bucket.public_web.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_versioning" "admin_web" {
  bucket = aws_s3_bucket.admin_web.id
  versioning_configuration { status = "Enabled" }
}

# Buckets 100% privados: nadie entra directo, solo CloudFront vía OAC.
resource "aws_s3_bucket_public_access_block" "public_web" {
  bucket                  = aws_s3_bucket.public_web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "admin_web" {
  bucket                  = aws_s3_bucket.admin_web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "media" {
  bucket                  = aws_s3_bucket.media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Cifrado en reposo (SSE-S3).
resource "aws_s3_bucket_server_side_encryption_configuration" "public_web" {
  bucket = aws_s3_bucket.public_web.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "admin_web" {
  bucket = aws_s3_bucket.admin_web.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Origin Access Control — CloudFront accede al bucket sin hacerlo público
resource "aws_cloudfront_origin_access_control" "this" {
  name                              = "${local.name_prefix}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Distribuciones CloudFront (una por app)
locals {
  s3_origin_id_public = "s3-public-web"
  s3_origin_id_admin  = "s3-admin-web"
  api_origin_id       = "api-gateway"
}

# Caché de edge para las LECTURAS públicas del API (TTL corto). Es la pieza clave
# de la respuesta a "cómo gestionar grandes volúmenes de tráfico": ante contenido
# viral, CloudFront responde /articles y /daily-summary desde el edge y el backend
# solo ve una fracción de las peticiones (1 origen cada ~30 s por PoP).
resource "aws_cloudfront_cache_policy" "api_short" {
  name        = "${local.name_prefix}-api-short-ttl"
  default_ttl = 30
  min_ttl     = 0
  max_ttl     = 60

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true
    cookies_config { cookie_behavior = "none" }
    headers_config { header_behavior = "none" }
    query_strings_config { query_string_behavior = "all" }
  }
}

# --- Web pública -------------------------------------------------------------
resource "aws_cloudfront_distribution" "public_web" {
  enabled             = true
  default_root_object = "index.html"
  comment             = "${local.name_prefix} public web"
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.public_web.bucket_regional_domain_name
    origin_id                = local.s3_origin_id_public
    origin_access_control_id = aws_cloudfront_origin_access_control.this.id
  }

  # Segundo origen: el API HTTP. Así la web pública y el API comparten dominio
  # (mismo origen, sin CORS) y las lecturas se cachean en el edge.
  origin {
    domain_name = "${aws_apigatewayv2_api.http.id}.execute-api.${var.aws_region}.amazonaws.com"
    origin_id   = local.api_origin_id
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = local.s3_origin_id_public
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # Caché gestionada de AWS "CachingOptimized" — clave para absorber picos.
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  # Lecturas públicas del API cacheadas en el edge (TTL corto). Las escrituras
  # (POST/PUT/DELETE) llevan JWT y van directas al API, no por este camino.
  ordered_cache_behavior {
    path_pattern           = "/articles*"
    target_origin_id       = local.api_origin_id
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = aws_cloudfront_cache_policy.api_short.id
  }

  ordered_cache_behavior {
    path_pattern           = "/daily-summary*"
    target_origin_id       = local.api_origin_id
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = aws_cloudfront_cache_policy.api_short.id
  }

  # SPA: cualquier ruta 403/404 devuelve index.html (routing en cliente).
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# --- Panel admin -------------------------------------------------------------
resource "aws_cloudfront_distribution" "admin_web" {
  enabled             = true
  default_root_object = "index.html"
  comment             = "${local.name_prefix} admin web"
  price_class         = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.admin_web.bucket_regional_domain_name
    origin_id                = local.s3_origin_id_admin
    origin_access_control_id = aws_cloudfront_origin_access_control.this.id
  }

  default_cache_behavior {
    target_origin_id       = local.s3_origin_id_admin
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Política de bucket: solo CloudFront (vía OAC) puede leer los objetos
data "aws_iam_policy_document" "public_web_s3" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.public_web.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.public_web.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "public_web" {
  bucket = aws_s3_bucket.public_web.id
  policy = data.aws_iam_policy_document.public_web_s3.json
}

data "aws_iam_policy_document" "admin_web_s3" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.admin_web.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.admin_web.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "admin_web" {
  bucket = aws_s3_bucket.admin_web.id
  policy = data.aws_iam_policy_document.admin_web_s3.json
}
