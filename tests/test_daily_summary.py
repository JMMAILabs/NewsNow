"""Lambda del resumen diario: junta los resúmenes del día y genera el boletín."""

import daily_summary as ds


class FakeTable:
    def __init__(self, items):
        self.by_key = {(i["PK"], i["SK"]): i for i in items}
        self._items = items
        self.written = []

    def query(self, **_kw):
        # el fake ignora la condición: devuelve las filas META
        return {"Items": [i for i in self._items if i.get("SK") == "META"]}

    def get_item(self, Key):
        item = self.by_key.get((Key["PK"], Key["SK"]))
        return {"Item": item} if item else {}

    def put_item(self, Item):
        self.written.append(Item)


def test_genera_el_boletin(monkeypatch):
    items = [
        {"PK": "ARTICLE#a1", "SK": "META", "title": "t1", "category": "tec"},
        {"PK": "ARTICLE#a1", "SK": "SUMMARY", "headline": "h1", "summary": "s1"},
        {"PK": "ARTICLE#a2", "SK": "META", "title": "t2", "category": "eco"},
        {"PK": "ARTICLE#a2", "SK": "SUMMARY", "headline": "h2", "summary": "s2"},
    ]
    monkeypatch.setattr(ds, "_table", FakeTable(items))
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
    monkeypatch.setattr(ds, "_table", FakeTable([]))
    result = ds.lambda_handler({"date": "2026-07-24"})
    assert result["status"] == "empty"
