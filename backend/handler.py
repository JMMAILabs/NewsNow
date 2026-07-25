"""
NewsNow — API REST (backend).

Lambda que resuelve el CRUD de artículos sobre DynamoDB (diseño single-table).
Se invoca desde API Gateway (HTTP API, payload v2.0).

Rutas:
    GET    /articles            → lista artículos publicados (portada)
    GET    /articles/{id}       → un artículo + su resumen
    GET    /daily-summary       → resumen diario más reciente
    POST   /articles            → crea artículo            (requiere JWT)
    PUT    /articles/{id}       → edita artículo           (requiere JWT)
    DELETE /articles/{id}       → elimina artículo         (requiere JWT)

El diseño evita frameworks pesados: un router mínimo mantiene la Lambda ligera
y con arranque en frío bajo.
"""

import json
import os
import random
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ.get("TABLE_NAME", "newsnow-dev-content")

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(TABLE_NAME)

# Repartimos los artículos del día en varios shards del GSI (DATE#<fecha>#<shard>)
# para no crear una hot partition bajo picos; al leer hacemos fan-in sobre todos.
# DEBE COINCIDIR con ai/daily_summary.py.
GSI_SHARDS = 10

# DynamoDB limita cada item a 400 KB; acotamos el cuerpo con margen para no petar
# con un 500 opaco en el PutItem.
MAX_BODY_BYTES = 350_000


# helpers

class _DecimalEncoder(json.JSONEncoder):
    # DynamoDB devuelve los números como Decimal y json no los sabe serializar.
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def _response(status: int, body) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",  # redes abiertas (enunciado)
        },
        "body": json.dumps(body, cls=_DecimalEncoder, ensure_ascii=False),
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


# operaciones CRUD

def list_articles(_event) -> dict:
    """Portada: los 50 artículos más recientes de hoy.

    El GSI reparte el día en shards (DATE#<fecha>#<shard>) para evitar una hot
    partition en picos, así que consultamos los shards (fan-in), deduplicamos por PK
    y nos quedamos con los 50 más recientes por fecha.
    """
    today = _today()
    items: dict[str, dict] = {}
    for shard in range(GSI_SHARDS):
        result = _table.query(
            IndexName="GSI1-by-date",
            KeyConditionExpression=Key("GSI1PK").eq(f"DATE#{today}#{shard}"),
            ScanIndexForward=False,
            Limit=50,
        )
        for i in result.get("Items", []):
            if i.get("SK") == "META":
                items[i["PK"]] = i
    top = sorted(items.values(), key=lambda a: a.get("GSI1SK", ""), reverse=True)[:50]
    return _response(200, {"articles": top, "count": len(top)})


def get_article(article_id: str) -> dict:
    """Devuelve el artículo y su resumen (si existe)."""
    meta = _table.get_item(Key={"PK": f"ARTICLE#{article_id}", "SK": "META"}).get("Item")
    if not meta:
        return _response(404, {"error": "article not found"})

    summary = _table.get_item(
        Key={"PK": f"ARTICLE#{article_id}", "SK": "SUMMARY"}
    ).get("Item")

    return _response(200, {"article": meta, "summary": summary})


def get_daily_summary(_event) -> dict:
    """Devuelve el resumen diario de hoy."""
    item = _table.get_item(
        Key={"PK": f"DAILY#{_today()}", "SK": "SUMMARY"}
    ).get("Item")
    if not item:
        return _response(404, {"error": "daily summary not available yet"})
    return _response(200, item)


def create_article(event) -> dict:
    """Crea un artículo nuevo en estado DRAFT (el resumen se genera aparte)."""
    body = json.loads(event.get("body") or "{}")
    if not body.get("title") or not body.get("body"):
        return _response(400, {"error": "'title' and 'body' are required"})
    if len(body["body"].encode("utf-8")) > MAX_BODY_BYTES:
        return _response(413, {"error": "'body' too large"})

    article_id = str(uuid.uuid4())
    now = _now_iso()
    today = _today()

    item = {
        "PK": f"ARTICLE#{article_id}",
        "SK": "META",
        "id": article_id,
        "title": body["title"],
        "body": body["body"],
        "author": body.get("author", "unknown"),
        "category": body.get("category", "general"),
        "status": "DRAFT",  # pasa a READY cuando la IA genera el resumen
        "created_at": now,
        "updated_at": now,
        # Claves del GSI para consultar por fecha (shard aleatorio → sin hot partition).
        "GSI1PK": f"DATE#{today}#{random.randint(0, GSI_SHARDS - 1)}",  # noqa: S311
        "GSI1SK": now,
    }
    _table.put_item(Item=item)
    return _response(201, {"id": article_id, "status": "DRAFT"})


def update_article(article_id: str, event) -> dict:
    """Edita un artículo existente."""
    existing = _table.get_item(
        Key={"PK": f"ARTICLE#{article_id}", "SK": "META"}
    ).get("Item")
    if not existing:
        return _response(404, {"error": "article not found"})

    body = json.loads(event.get("body") or "{}")
    new_body = body.get("body", existing["body"])
    if len(new_body.encode("utf-8")) > MAX_BODY_BYTES:
        return _response(413, {"error": "'body' too large"})
    existing.update(
        {
            "title": body.get("title", existing["title"]),
            "body": new_body,
            "category": body.get("category", existing.get("category", "general")),
            "status": "DRAFT",  # al editar, se regenera el resumen
            "updated_at": _now_iso(),
        }
    )
    _table.put_item(Item=existing)
    return _response(200, {"id": article_id, "status": "updated"})


def delete_article(article_id: str) -> dict:
    """Elimina el artículo y su resumen asociado."""
    existing = _table.get_item(
        Key={"PK": f"ARTICLE#{article_id}", "SK": "META"}
    ).get("Item")
    if not existing:
        return _response(404, {"error": "article not found"})
    _table.delete_item(Key={"PK": f"ARTICLE#{article_id}", "SK": "META"})
    _table.delete_item(Key={"PK": f"ARTICLE#{article_id}", "SK": "SUMMARY"})
    return _response(200, {"id": article_id, "status": "deleted"})


# router

def lambda_handler(event, _context=None):
    """Punto de entrada; enruta por método + path (API Gateway HTTP API v2)."""
    try:
        method = event["requestContext"]["http"]["method"]
        path = event["requestContext"]["http"]["path"]
        path_params = event.get("pathParameters") or {}
        article_id = path_params.get("id")

        if method == "GET" and path == "/articles":
            return list_articles(event)
        if method == "GET" and path == "/daily-summary":
            return get_daily_summary(event)
        if method == "GET" and article_id:
            return get_article(article_id)
        if method == "POST" and path == "/articles":
            return create_article(event)
        if method == "PUT" and article_id:
            return update_article(article_id, event)
        if method == "DELETE" and article_id:
            return delete_article(article_id)

        return _response(404, {"error": f"route not found: {method} {path}"})

    except Exception as exc:  # noqa: BLE001 — 500 controlado
        # El detalle va al log (CloudWatch), nunca al cliente: evita fuga de info.
        print(f"[api] error no controlado: {exc}")
        return _response(500, {"error": "internal error"})
