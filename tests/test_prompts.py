"""Contrato de los prompts.

No podemos comprobar la *calidad* del resumen sin llamar al modelo real (eso se
valida aparte, p. ej. en PartyRock), pero sí podemos blindar que las instrucciones
críticas siguen estando en los prompts: fidelidad, neutralidad, JSON estricto y las
claves esperadas. Si alguien las borra sin querer, estos tests fallan.
"""

import bedrock_client as bc


def test_system_prompt_exige_fidelidad_y_neutralidad():
    p = bc.SYSTEM_PROMPT.lower()
    assert "no inventes" in p or "fidelidad" in p
    assert "neutral" in p


def test_system_prompt_exige_json_sin_markdown():
    p = bc.SYSTEM_PROMPT.lower()
    assert "json" in p
    assert "markdown" in p  # prohíbe explícitamente markdown / bloques de código


def test_summary_prompt_pide_las_tres_claves():
    p = bc._build_summary_prompt("Un titular", "Un cuerpo de noticia.")
    for clave in ("headline", "summary", "tags"):
        assert f'"{clave}"' in p


def test_daily_prompt_sintetiza_solo_lo_dado():
    p = bc._build_daily_prompt([{"title": "x", "summary": "s"}])
    assert "sintetizando" in p.lower() or "únicamente" in p.lower()
    for clave in ("intro", "highlights", "digest"):
        assert f'"{clave}"' in p
