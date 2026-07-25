"""
Lambda del resumen individual.

La dispara DynamoDB Streams al crear/editar un artículo (fila SK=META en estado
DRAFT): llama a Bedrock, guarda el resumen (SK=SUMMARY) y marca el artículo READY.

Solo procesa borradores (DRAFT). Marcar READY genera otro MODIFY sobre la misma
fila META que vuelve por el stream; el corte por estado evita un bucle de
re-resumen (y de coste en Bedrock). Además es idempotente: reprocesar el mismo
evento solo sobrescribe el resumen.
"""

import os

import boto3
from bedrock_client import summarize_article

TABLE_NAME = os.environ.get("TABLE_NAME", "newsnow-dev-content")
_table = boto3.resource("dynamodb").Table(TABLE_NAME)


def _deserialize(image: dict) -> dict:
    """Convierte una imagen de DynamoDB Streams (formato tipado) a dict plano."""
    from boto3.dynamodb.types import TypeDeserializer

    d = TypeDeserializer()
    return {k: d.deserialize(v) for k, v in image.items()}


def _process_article(article: dict) -> None:
    article_id = article["id"]
    result = summarize_article(article["title"], article["body"])

    _table.put_item(
        Item={
            "PK": f"ARTICLE#{article_id}",
            "SK": "SUMMARY",
            "id": article_id,
            "headline": result.get("headline", ""),
            "summary": result.get("summary", ""),
            "tags": result.get("tags", []),
            "model": os.environ.get("BEDROCK_MODEL_ID", "mock"),
        }
    )

    # Marca el artículo como listo para publicarse.
    _table.update_item(
        Key={"PK": f"ARTICLE#{article_id}", "SK": "META"},
        UpdateExpression="SET #s = :ready",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":ready": "READY"},
    )
    print(f"[summarize] artículo {article_id} resumido y marcado READY")


def lambda_handler(event, _context=None):
    """Procesa el batch de registros del stream.

    Devuelve `batchItemFailures` (ReportBatchItemFailures): si un registro falla,
    Lambda reintenta SOLO ese, no el batch entero. Así un artículo problemático
    no obliga a reprocesar (ni re-resumir) los que ya salieron bien bajo carga.
    """
    failures = []

    for record in event.get("Records", []):
        if record.get("eventName") not in ("INSERT", "MODIFY"):
            continue
        new_image = record["dynamodb"].get("NewImage")
        if not new_image:
            continue

        article = _deserialize(new_image)
        # solo nos interesan las filas META (el artículo), no las de SUMMARY
        if article.get("SK") != "META":
            continue
        # solo resumimos borradores: al marcar READY se produce otro MODIFY de la
        # fila META que vuelve por el stream; sin este corte sería un bucle infinito.
        if article.get("status") != "DRAFT":
            continue

        try:
            _process_article(article)
        except Exception as exc:  # noqa: BLE001 — reintentar solo este registro
            seq = record["dynamodb"].get("SequenceNumber", record.get("eventID", ""))
            print(f"[summarize] fallo procesando {article.get('id')}: {exc}")
            failures.append({"itemIdentifier": seq})

    return {"batchItemFailures": failures}
