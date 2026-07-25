"""
NewsNow — API REST (backend).

Lambda que resuelve el CRUD de artículos sobre DynamoDB (diseño single-table).
Se invoca desde API Gateway (HTTP API, payload v2.0).

Rutas:
    GET    /articles            → portada: publicados (READY) + su resumen de IA
    GET    /articles?view=admin → panel: última semana, todos los estados + cuerpo
    GET    /articles/{id}       → un artículo + su resumen
    GET    /daily-summary       → boletín de la jornada anterior
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
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

TABLE_NAME = os.environ.get("TABLE_NAME", "newsnow-dev-content")

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(TABLE_NAME)

# Repartimos los artículos del día en varios shards del GSI (DATE#<fecha>#<shard>)
# para no crear una hot partition bajo picos; al leer hacemos fan-in sobre todos.
# Terraform inyecta el mismo valor (var.gsi_shards) aquí y en el resumen diario, así
# ambos quedan sincronizados desde una única fuente (sin constantes que "deban coincidir").
GSI_SHARDS = int(os.environ.get("GSI_SHARDS", "10"))

# DynamoDB limita cada item a 400 KB; acotamos el cuerpo con margen para no petar
# con un 500 opaco en el PutItem.
MAX_BODY_BYTES = 350_000

# El panel admin gestiona los artículos de la última semana (no solo los de hoy).
ADMIN_WINDOW_DAYS = 7


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


def _yesterday() -> str:
    return (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")


def _recent_dates(n: int) -> list[str]:
    """Las últimas n fechas (hoy incluido), como 'YYYY-MM-DD'."""
    base = datetime.now(UTC)
    return [(base - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


# operaciones CRUD

def _batch_get_summaries(pks: list[str]) -> dict[str, dict]:
    """SUMMARY de varios artículos con BatchGetItem (reintenta UnprocessedKeys)."""
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


def _query_metas(dates: list[str]) -> dict[str, dict]:
    """Fan-in sobre (fecha × shard) del GSI por fecha, deduplicado por PK."""
    metas: dict[str, dict] = {}
    for date in dates:
        for shard in range(GSI_SHARDS):
            result = _table.query(
                IndexName="GSI1-by-date",
                KeyConditionExpression=Key("GSI1PK").eq(f"DATE#{date}#{shard}"),
                ScanIndexForward=False,
                Limit=50,
            )
            for i in result.get("Items", []):
                if i.get("SK") == "META":
                    metas[i["PK"]] = i
    return metas


def list_articles(event) -> dict:
    """Lista de artículos (fan-in sobre los shards del GSI, dedup + orden por fecha).

    Dos vistas sobre el mismo endpoint:
    - **pública** (por defecto): artículos de **hoy** en estado **READY** y con su
      **resumen de IA** (headline/summary/tags), sin el cuerpo → tarjetas de portada.
      Es la que cachea CloudFront.
    - **admin** (`?view=admin`): la **última semana** en todos los estados (incluidos
      borradores), con cuerpo y `status`, para gestionar los artículos desde el panel.
    """
    view = (event.get("queryStringParameters") or {}).get("view", "public")

    if view == "admin":
        metas = _query_metas(_recent_dates(ADMIN_WINDOW_DAYS))
        ordered = sorted(metas.values(), key=lambda a: a.get("GSI1SK", ""), reverse=True)
        top = ordered[:50]
        return _response(200, {"articles": top, "count": len(top)})

    # Vista pública: solo hoy, solo publicados (READY) + su resumen de IA, sin el cuerpo.
    metas = _query_metas([_today()])
    ordered = sorted(metas.values(), key=lambda a: a.get("GSI1SK", ""), reverse=True)
    ready = [m for m in ordered if m.get("status") == "READY"][:50]
    summaries = _batch_get_summaries([m["PK"] for m in ready])
    articles = []
    for meta in ready:
        s = summaries.get(meta["PK"], {})
        articles.append(
            {
                "id": meta.get("id"),
                "title": meta.get("title"),
                "category": meta.get("category", "general"),
                "headline": s.get("headline"),
                "summary": s.get("summary"),
                "tags": s.get("tags", []),
                "created_at": meta.get("created_at"),
            }
        )
    return _response(200, {"articles": articles, "count": len(articles)})


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
    """Devuelve el boletín de la jornada anterior (se genera cada madrugada)."""
    item = _table.get_item(
        Key={"PK": f"DAILY#{_yesterday()}", "SK": "SUMMARY"}
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
