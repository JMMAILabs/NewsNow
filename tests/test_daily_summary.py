"""Lambda del resumen diario: junta los resúmenes del día y genera el boletín."""

import daily_summary as ds


class FakeTable:
    """Doble de la tabla + del recurso DynamoDB (query, batch_get_item, put_item).

    `query` ignora el shard y devuelve siempre las filas META; como la Lambda hace
    fan-in sobre 10 shards, el dedup por PK del código debe colapsarlas a las únicas.
    """

    def __init__(self, items):
        self.by_key = {(i["PK"], i["SK"]): i for i in items}
        self._items = items
        self.written = []

    def query(self, **_kw):
        return {"Items": [i for i in self._items if i.get("SK") == "META"]}

    def batch_get_item(self, RequestItems):
        table = next(iter(RequestItems))
        keys = RequestItems[table]["Keys"]
        found = [
            self.by_key[(k["PK"], k["SK"])]
            for k in keys
            if (k["PK"], k["SK"]) in self.by_key
        ]
        return {"Responses": {table: found}}

    def put_item(self, Item):
        self.written.append(Item)


def test_genera_el_boletin(monkeypatch):
    items = [
        {"PK": "ARTICLE#a1", "SK": "META", "title": "t1", "category": "tec"},
        {"PK": "ARTICLE#a1", "SK": "SUMMARY", "headline": "h1", "summary": "s1"},
        {"PK": "ARTICLE#a2", "SK": "META", "title": "t2", "category": "eco"},
        {"PK": "ARTICLE#a2", "SK": "SUMMARY", "headline": "h2", "summary": "s2"},
    ]
    fake = FakeTable(items)
    monkeypatch.setattr(ds, "_table", fake)
    monkeypatch.setattr(ds, "_dynamodb", fake)  # batch_get_item vive en el recurso
    monkeypatch.setattr(
        ds, "summarize_day",
        lambda _its: {"intro": "i", "highlights": ["h1", "h2"], "digest": "d"},
    )

    table = ds._table
    result = ds.lambda_handler({"date": "2026-07-24"})

    assert result["articles"] == 2
    assert result["status"] == "ok"
    assert any(w["PK"] == "DAILY#2026-07-24" for w in table.written)


def test_dia_sin_articulos(monkeypatch):
    fake = FakeTable([])
    monkeypatch.setattr(ds, "_table", fake)
    monkeypatch.setattr(ds, "_dynamodb", fake)
    result = ds.lambda_handler({"date": "2026-07-24"})
    assert result["status"] == "empty"
