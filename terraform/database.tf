# database.tf — DynamoDB (artículos + resúmenes), diseño single-table
# Modo on-demand (PAY_PER_REQUEST): escala automáticamente con el tráfico sin
# planificar capacidad. Streams habilitado para disparar la IA event-driven.

resource "aws_dynamodb_table" "content" {
  name         = "${local.name_prefix}-content"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "PK"
  range_key = "SK"

  attribute {
    name = "PK"
    type = "S"
  }
  attribute {
    name = "SK"
    type = "S"
  }

  # Atributos del GSI para consultar artículos por fecha (portada + resumen diario).
  attribute {
    name = "GSI1PK"
    type = "S"
  }
  attribute {
    name = "GSI1SK"
    type = "S"
  }

  global_secondary_index {
    name            = "GSI1-by-date"
    hash_key        = "GSI1PK" # DATE#yyyy-mm-dd#shard (sharded para evitar hot partition)
    range_key       = "GSI1SK" # created_at (ISO8601)
    projection_type = "ALL"    # la portada lee title/category del propio índice
  }

  # Streams: cada INSERT/MODIFY dispara la generación de resúmenes.
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery {
    enabled = true
  }
}
