"""Lambda de resumen individual: idempotencia, batch y fallos parciales.

Estas son las propiedades que *habilitan* escalar (entrega at-least-once de los
Streams): que reprocesar el mismo evento no duplique nada y que un registro malo
no tumbe todo el batch.
"""

import summarize_article as sa


class FakeTable:
    """DynamoDB en memoria, lo justo para estas pruebas."""

    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        self.items[(Item["PK"], Item["SK"])] = Item

    def get_item(self, Key):
        item = self.items.get((Key["PK"], Key["SK"]))
        return {"Item": item} if item else {}

    def update_item(self, Key, ExpressionAttributeValues=None, **_kw):
        item = self.items.setdefault((Key["PK"], Key["SK"]), dict(Key))
        if ExpressionAttributeValues and ":ready" in ExpressionAttributeValues:
            item["status"] = ExpressionAttributeValues[":ready"]


def _meta_record(article_id, title="Titular", body="Cuerpo.", seq="1"):
    image = {
        "PK": {"S": f"ARTICLE#{article_id}"},
        "SK": {"S": "META"},
        "id": {"S": article_id},
        "title": {"S": title},
    }
    if body is not None:
        image["body"] = {"S": body}
    return {"eventName": "INSERT", "dynamodb": {"SequenceNumber": seq, "NewImage": image}}


def _stub_summary(_title, _body):
    return {"headline": "H", "summary": "S", "tags": ["t"]}


def _setup(monkeypatch):
    table = FakeTable()
    monkeypatch.setattr(sa, "_table", table)
    monkeypatch.setattr(sa, "summarize_article", _stub_summary)
    return table


def test_procesa_el_batch(monkeypatch):
    table = _setup(monkeypatch)
    event = {"Records": [_meta_record("a1", seq="1"), _meta_record("a2", seq="2")]}

    result = sa.lambda_handler(event)

    assert result["batchItemFailures"] == []
    assert ("ARTICLE#a1", "SUMMARY") in table.items
    assert table.items[("ARTICLE#a1", "META")]["status"] == "READY"


def test_es_idempotente(monkeypatch):
    table = _setup(monkeypatch)
    event = {"Records": [_meta_record("a1", seq="1")]}

    sa.lambda_handler(event)
    primero = dict(table.items[("ARTICLE#a1", "SUMMARY")])
    sa.lambda_handler(event)  # mismo evento otra vez (at-least-once)
    segundo = table.items[("ARTICLE#a1", "SUMMARY")]

    assert primero == segundo  # mismo resultado, sin duplicar ni corromper


def test_fallo_parcial_solo_reintenta_ese(monkeypatch):
    table = _setup(monkeypatch)
    # el segundo registro no trae "body" -> _process_article revienta
    event = {"Records": [
        _meta_record("ok", seq="10"),
        _meta_record("malo", body=None, seq="20"),
    ]}

    result = sa.lambda_handler(event)

    assert result["batchItemFailures"] == [{"itemIdentifier": "20"}]
    assert ("ARTICLE#ok", "SUMMARY") in table.items  # el bueno sí se guardó
