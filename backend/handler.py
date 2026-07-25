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
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ.get("TABLE_NAME", "newsnow-dev-content")

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(TABLE_NAME)


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
    """Portada: los 50 artículos más recientes de hoy (GSI por fecha).

    Acotamos con `Limit` para no traer el día entero de golpe (un `query` sin límite
    devuelve hasta 1 MB y podría cortar en seco); la paginación al cliente vía cursor
    `LastEvaluatedKey` queda como siguiente paso.
    """
    result = _table.query(
        IndexName="GSI1-by-date",
        KeyConditionExpression=Key("GSI1PK").eq(f"DATE#{_today()}"),
        ScanIndexForward=False,
        Limit=50,
    )
    items = [i for i in result.get("Items", []) if i.get("SK") == "META"]
    return _response(200, {"articles": items, "count": len(items)})


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
        # Claves del GSI para consultar por fecha.
        "GSI1PK": f"DATE#{today}",
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
    existing.update(
        {
            "title": body.get("title", existing["title"]),
            "body": body.get("body", existing["body"]),
            "category": body.get("category", existing.get("category", "general")),
            "status": "DRAFT",  # al editar, se regenera el resumen
            "updated_at": _now_iso(),
        }
    )
    _table.put_item(Item=existing)
    return _response(200, {"id": article_id, "status": "updated"})


def delete_article(article_id: str) -> dict:
    """Elimina el artículo y su resumen asociado."""
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
