"""API REST (backend): fan-in de portada, validación de tamaño y borrado 404."""

import json

import handler


class FakeTable:
    """Doble de la tabla. `query` ignora el shard y devuelve todas las META; como
    `list_articles` hace fan-in sobre N shards, el dedup por PK del código debe
    colapsarlas a las únicas."""

    def __init__(self, items=None):
        self.by_key = {}
        self.metas = []
        for it in items or []:
            self.by_key[(it["PK"], it["SK"])] = it
            if it.get("SK") == "META":
                self.metas.append(it)
        self.deleted = []
        self.put = []

    def query(self, **_kw):
        return {"Items": list(self.metas)}

    def get_item(self, Key):
        item = self.by_key.get((Key["PK"], Key["SK"]))
        return {"Item": item} if item else {}

    def put_item(self, Item):
        self.put.append(Item)

    def delete_item(self, Key):
        self.deleted.append((Key["PK"], Key["SK"]))


def _meta(article_id, ts):
    return {"PK": f"ARTICLE#{article_id}", "SK": "META", "id": article_id,
            "title": article_id, "GSI1SK": ts}


def test_portada_deduplica_y_ordena_por_fecha(monkeypatch):
    items = [
        _meta("a1", "2026-07-24T10:00:00"),
        _meta("a2", "2026-07-24T12:00:00"),
        _meta("a3", "2026-07-24T08:00:00"),
    ]
    monkeypatch.setattr(handler, "_table", FakeTable(items))
    body = json.loads(handler.list_articles({})["body"])
    # pese al fan-in sobre los shards, cada artículo aparece una sola vez
    assert body["count"] == 3
    # y salen ordenados por fecha descendente (más reciente primero)
    assert [a["id"] for a in body["articles"]] == ["a2", "a1", "a3"]


def test_create_rechaza_cuerpo_demasiado_grande(monkeypatch):
    monkeypatch.setattr(handler, "_table", FakeTable())
    event = {"body": json.dumps({"title": "t", "body": "x" * (handler.MAX_BODY_BYTES + 1)})}
    assert handler.create_article(event)["statusCode"] == 413


def test_create_asigna_shard_en_el_gsi(monkeypatch):
    fake = FakeTable()
    monkeypatch.setattr(handler, "_table", fake)
    resp = handler.create_article({"body": json.dumps({"title": "t", "body": "cuerpo"})})
    assert resp["statusCode"] == 201
    # GSI1PK = DATE#<fecha>#<shard>  → tiene el shard al final
    partes = fake.put[0]["GSI1PK"].split("#")
    assert partes[0] == "DATE" and partes[2].isdigit()


def test_daily_summary_lee_la_jornada_anterior(monkeypatch):
    ayer = handler._yesterday()
    fake = FakeTable()
    fake.by_key[(f"DAILY#{ayer}", "SUMMARY")] = {
        "PK": f"DAILY#{ayer}", "SK": "SUMMARY", "digest": "boletin de ayer",
    }
    monkeypatch.setattr(handler, "_table", fake)
    resp = handler.get_daily_summary({})
    assert resp["statusCode"] == 200
    assert "ayer" in json.loads(resp["body"])["digest"]


def test_daily_summary_404_si_no_esta(monkeypatch):
    monkeypatch.setattr(handler, "_table", FakeTable())
    assert handler.get_daily_summary({})["statusCode"] == 404


def test_delete_inexistente_devuelve_404(monkeypatch):
    monkeypatch.setattr(handler, "_table", FakeTable())
    assert handler.delete_article("nope")["statusCode"] == 404


def test_delete_existente_borra_meta_y_summary(monkeypatch):
    fake = FakeTable([_meta("a1", "2026-07-24T10:00:00")])
    monkeypatch.setattr(handler, "_table", fake)
    resp = handler.delete_article("a1")
    assert resp["statusCode"] == 200
    assert ("ARTICLE#a1", "META") in fake.deleted
    assert ("ARTICLE#a1", "SUMMARY") in fake.deleted
