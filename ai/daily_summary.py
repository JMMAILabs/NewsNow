"""
Lambda del resumen diario (el boletín).

La dispara EventBridge Scheduler una vez al día. Junta los resúmenes de los
artículos de la jornada (GSI por fecha), pide a Bedrock el digest y lo guarda
como DAILY#<fecha>.

Map-reduce a propósito: no mandamos los cuerpos enteros (caro y no cabe en el
contexto), sino los resúmenes ya calculados por la otra Lambda → resumen de
resúmenes.
"""

import os
from datetime import UTC, datetime

import boto3
from bedrock_client import summarize_day
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ.get("TABLE_NAME", "newsnow-dev-content")
_table = boto3.resource("dynamodb").Table(TABLE_NAME)


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _collect_summaries(date: str) -> list[dict]:
    """Une, por cada artículo del día, sus metadatos con su resumen."""
    # El boletín necesita TODOS los artículos del día → paginamos el query
    # (un solo query devuelve hasta 1 MB; sin el bucle perderíamos artículos).
    kwargs = {
        "IndexName": "GSI1-by-date",
        "KeyConditionExpression": Key("GSI1PK").eq(f"DATE#{date}"),
    }
    resp = _table.query(**kwargs)
    metas = [i for i in resp.get("Items", []) if i.get("SK") == "META"]
    while resp.get("LastEvaluatedKey"):
        resp = _table.query(**kwargs, ExclusiveStartKey=resp["LastEvaluatedKey"])
        metas.extend(i for i in resp.get("Items", []) if i.get("SK") == "META")

    # N+1: un get_item por artículo. Para el MVP sobra; en prod usaría BatchGetItem.
    items = []
    for meta in metas:
        summary = _table.get_item(
            Key={"PK": meta["PK"], "SK": "SUMMARY"}
        ).get("Item")
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
    date = (event or {}).get("date") or _today()
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
