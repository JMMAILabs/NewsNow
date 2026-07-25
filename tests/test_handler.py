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

    def batch_get_item(self, RequestItems):
        table = next(iter(RequestItems))
        keys = RequestItems[table]["Keys"]
        found = [
            self.by_key[(k["PK"], k["SK"])]
            for k in keys
            if (k["PK"], k["SK"]) in self.by_key
        ]
        return {"Responses": {table: found}}

    def get_item(self, Key):
        item = self.by_key.get((Key["PK"], Key["SK"]))
        return {"Item": item} if item else {}

    def put_item(self, Item):
        self.put.append(Item)

    def delete_item(self, Key):
        self.deleted.append((Key["PK"], Key["SK"]))


def _meta(article_id, ts, status="READY"):
    return {"PK": f"ARTICLE#{article_id}", "SK": "META", "id": article_id,
            "title": article_id, "body": "cuerpo", "category": "tec",
            "status": status, "GSI1SK": ts}


def _summary(article_id):
    return {"PK": f"ARTICLE#{article_id}", "SK": "SUMMARY",
            "headline": f"h-{article_id}", "summary": f"s-{article_id}", "tags": ["t"]}


def test_portada_publica_solo_ready_con_resumen(monkeypatch):
    items = [
        _meta("a1", "2026-07-24T10:00:00"), _summary("a1"),
        _meta("a2", "2026-07-24T12:00:00"), _summary("a2"),
        _meta("a3", "2026-07-24T08:00:00", status="DRAFT"),  # borrador: no debe salir
    ]
    fake = FakeTable(items)
    monkeypatch.setattr(handler, "_table", fake)
    monkeypatch.setattr(handler, "_dynamodb", fake)  # BatchGetItem vive en el recurso

    body = json.loads(handler.list_articles({})["body"])

    assert [a["id"] for a in body["articles"]] == ["a2", "a1"]  # solo READY, por fecha
    assert body["articles"][0]["summary"] == "s-a2"            # trae el resumen de IA
    assert "body" not in body["articles"][0]                   # sin el cuerpo completo


def test_vista_admin_incluye_borradores_y_status(monkeypatch):
    items = [
        _meta("a1", "2026-07-24T10:00:00"),
        _meta("a2", "2026-07-24T12:00:00", status="DRAFT"),
    ]
    monkeypatch.setattr(handler, "_table", FakeTable(items))
    event = {"queryStringParameters": {"view": "admin"}}

    body = json.loads(handler.list_articles(event)["body"])

    assert sorted(a["id"] for a in body["articles"]) == ["a1", "a2"]  # incluye el borrador
    assert any(a.get("status") == "DRAFT" for a in body["articles"])  # con su status


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
