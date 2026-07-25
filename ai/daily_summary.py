"""
Lambda del resumen diario (el boletín).

La dispara EventBridge Scheduler cada madrugada. Junta los resúmenes de los
artículos de la JORNADA ANTERIOR (GSI por fecha), pide a Bedrock el digest y lo
guarda como DAILY#<fecha>. Se resume el día anterior porque el cron corre de
madrugada: a esa hora el día en curso apenas tiene noticias.

Map-reduce a propósito: no mandamos los cuerpos enteros (caro y no cabe en el
contexto), sino los resúmenes ya calculados por la otra Lambda → resumen de
resúmenes.
"""

import os
from datetime import UTC, datetime, timedelta

import boto3
from bedrock_client import summarize_day
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ.get("TABLE_NAME", "newsnow-dev-content")
_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(TABLE_NAME)

# Nº de shards del GSI por fecha (DATE#<fecha>#<shard>): reparte la escritura para
# evitar una hot partition bajo picos; al leer hacemos fan-in sobre todos. Terraform
# inyecta el mismo var.gsi_shards aquí y en el backend → una única fuente de verdad.
GSI_SHARDS = int(os.environ.get("GSI_SHARDS", "10"))


def _yesterday() -> str:
    return (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")


def _query_day_metas(date: str) -> list[dict]:
    """Fan-in con paginación sobre todos los shards del GSI por fecha (deduplicado)."""
    metas: dict[str, dict] = {}
    for shard in range(GSI_SHARDS):
        kwargs = {
            "IndexName": "GSI1-by-date",
            "KeyConditionExpression": Key("GSI1PK").eq(f"DATE#{date}#{shard}"),
        }
        resp = _table.query(**kwargs)
        while True:
            for item in resp.get("Items", []):
                if item.get("SK") == "META":
                    metas[item["PK"]] = item  # dedup por PK
            if not resp.get("LastEvaluatedKey"):
                break
            resp = _table.query(**kwargs, ExclusiveStartKey=resp["LastEvaluatedKey"])
    return list(metas.values())


def _batch_get_summaries(pks: list[str]) -> dict[str, dict]:
    """Trae los SUMMARY de varios artículos con BatchGetItem (máx. 100 por lote).

    Evita el N+1 (un GetItem por artículo) que a gran volumen agotaría el tiempo de
    la Lambda. Reintenta las `UnprocessedKeys`: bajo throttling o respuestas grandes,
    BatchGetItem puede devolver parte de las claves sin servir; sin reintentarlas se
    perderían resúmenes del boletín en silencio.
    """
    out: dict[str, dict] = {}
    for i in range(0, len(pks), 100):
        keys = [{"PK": pk, "SK": "SUMMARY"} for pk in pks[i : i + 100]]
        request = {TABLE_NAME: {"Keys": keys}}
        while request:
            resp = _dynamodb.batch_get_item(RequestItems=request)
            for item in resp.get("Responses", {}).get(TABLE_NAME, []):
                out[item["PK"]] = item
            request = resp.get("UnprocessedKeys") or None
    return out


def _collect_summaries(date: str) -> list[dict]:
    """Une, por cada artículo del día, sus metadatos con su resumen."""
    metas = _query_day_metas(date)
    if not metas:
        return []

    summaries = _batch_get_summaries([m["PK"] for m in metas])
    items = []
    for meta in metas:
        summary = summaries.get(meta["PK"])
        if summary:
            items.append(
                {
                    "title": meta.get("title"),
                    "category": meta.get("category", "general"),
                    "headline": summary.get("headline"),
                    "summary": summary.get("summary"),
                }
            )
    return items


def lambda_handler(event=None, _context=None):
    # Por defecto, la jornada anterior (el cron corre de madrugada). Se puede pasar
    # una fecha explícita en el evento para regenerar un día concreto (backfill).
    date = (event or {}).get("date") or _yesterday()
    items = _collect_summaries(date)

    if not items:
        print(f"[daily] sin artículos para {date}")
        return {"date": date, "articles": 0, "status": "empty"}

    digest = summarize_day(items)

    _table.put_item(
        Item={
            "PK": f"DAILY#{date}",
            "SK": "SUMMARY",
            "date": date,
            "intro": digest.get("intro", ""),
            "highlights": digest.get("highlights", []),
            "digest": digest.get("digest", ""),
            "article_count": len(items),
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    print(f"[daily] resumen diario {date} generado con {len(items)} artículos")
    return {"date": date, "articles": len(items), "status": "ok"}
