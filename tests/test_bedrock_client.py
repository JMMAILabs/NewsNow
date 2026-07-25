"""Tests del cliente de IA: funciones puras, sin tocar AWS."""

import bedrock_client as bc


def _sin_aws(*_a, **_k):
    # fuerza el camino mock (como si no hubiese credenciales de Bedrock)
    raise RuntimeError("sin AWS en test")


def test_truncar_frases_corta_en_frase_entera():
    texto = "Primera frase. Segunda frase larga que no cabe entera."
    assert bc._truncar_frases(texto, 20) == "Primera frase."


def test_truncar_frases_vacio():
    assert bc._truncar_frases("", 100) == ""


def test_parse_json_limpio():
    assert bc._parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_envuelto_en_texto():
    # el LLM real a veces mete texto alrededor del JSON; hay que ser tolerante
    raw = 'Claro:\n{"headline": "h", "summary": "s", "tags": []}\nEspero que sirva.'
    assert bc._parse_json(raw)["headline"] == "h"


def test_parse_json_basura_no_revienta():
    assert "summary" in bc._parse_json("esto no es json")


def test_summarize_article_devuelve_las_claves(monkeypatch):
    monkeypatch.setenv("NEWSNOW_ALLOW_MOCK", "1")
    monkeypatch.setattr(bc, "_invoke_bedrock", _sin_aws)
    out = bc.summarize_article("Titular", "Cuerpo de la noticia. Con dos frases.")
    assert set(out) >= {"headline", "summary", "tags"}
    assert isinstance(out["tags"], list)


def test_summarize_day_devuelve_boletin(monkeypatch):
    monkeypatch.setenv("NEWSNOW_ALLOW_MOCK", "1")
    monkeypatch.setattr(bc, "_invoke_bedrock", _sin_aws)
    items = [
        {"category": "tec", "headline": "h1", "summary": "resumen uno."},
        {"category": "eco", "headline": "h2", "summary": "resumen dos."},
    ]
    out = bc.summarize_day(items)
    assert set(out) >= {"intro", "highlights", "digest"}
