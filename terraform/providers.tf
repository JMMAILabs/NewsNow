# providers.tf — Provider AWS y configuración del backend de estado

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # --- Estado remoto (recomendado para trabajo en equipo) ---------------------
  # Descomentar y crear previamente el bucket + tabla de bloqueo.
  # backend "s3" {
  #   bucket         = "newsnow-terraform-state"
  #   key            = "global/terraform.tfstate"
  #   region         = "eu-west-1"
  #   dynamodb_table = "newsnow-terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# Nota: si más adelante se usa dominio propio + certificado ACM para CloudFront,
# hará falta un segundo provider "aws" con alias = "us_east_1" (los certificados
# de CloudFront viven en us-east-1). Ahora usamos el certificado por defecto, así
# que no lo declaramos para no dejar recursos sin usar.

# Sufijo aleatorio para nombres de bucket S3 (deben ser únicos globalmente).
resource "random_id" "suffix" {
  byte_length = 4
}
