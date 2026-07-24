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

  default_cache_behavior {
    target_origin_id       = local.s3_origin_id_public
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # Caché gestionada de AWS "CachingOptimized" — clave para absorber picos.
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
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
