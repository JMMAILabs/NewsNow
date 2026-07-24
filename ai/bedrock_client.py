"""
Cliente de Amazon Bedrock (Claude) que comparten las dos Lambdas de IA.

Si no hay credenciales de AWS o acceso a Bedrock, cae en un modo mock (resumen
extractivo local) para poder ejecutar el prototipo sin desplegar nada.
"""

import json
import os
import re

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5")
AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")

# Prompt de sistema: fija el rol y el formato de salida (JSON) del asistente.
SYSTEM_PROMPT = (
    "Eres el asistente editorial de NewsNow, un periódico digital. "
    "Resumes noticias de forma fiel, neutral y concisa en español. "
    "CRUCIAL: No inventas datos que no estén en el texto. "
    "Respondes SIEMPRE en JSON válido y estructurado, con las claves solicitadas."
)


def _build_summary_prompt(title: str, body: str) -> str:
    return (
        "Resume la siguiente noticia.\n"
        "Devuelve un JSON con exactamente estas claves:\n"
        '  - "headline": un titular alternativo breve (máx. 12 palabras)\n'
        '  - "summary": resumen de 2-3 frases (máx. 60 palabras)\n'
        '  - "tags": lista de 3-5 etiquetas temáticas en minúscula\n\n'
        f"TÍTULO: {title}\n\n"
        f"CUERPO:\n{body}\n"
    )


def _build_daily_prompt(items: list[dict]) -> str:
    bloques = "\n".join(
        f"- [{it.get('category', 'general')}] {it.get('headline') or it.get('title')}: "
        f"{it.get('summary', '')}"
        for it in items
    )
    return (
        "A partir de los resúmenes de las noticias de hoy, redacta el resumen "
        "diario de NewsNow.\n"
        "Devuelve un JSON con estas claves:\n"
        '  - "intro": frase de apertura del boletín (1 frase)\n'
        '  - "highlights": lista de 3-5 titulares destacados del día\n'
        '  - "digest": párrafo de 4-6 frases que sintetice la jornada\n\n'
        f"NOTICIAS DE HOY:\n{bloques}\n"
    )


def _invoke_bedrock(system: str, user_prompt: str, max_tokens: int = 512) -> str:
    import boto3  # perezoso: solo si de verdad hay AWS delante

    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    body = {
        # constante fija de la Messages API en Bedrock (no es una fecha que actualizar)
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": 0.2,  # baja = más fiel al texto
        "system": system,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    resp = client.invoke_model(modelId=MODEL_ID, body=json.dumps(body))
    payload = json.loads(resp["body"].read())
    return payload["content"][0]["text"]


# --- modo mock (sin AWS): resumen extractivo de andar por casa --------------

def _truncar_frases(texto: str, max_chars: int) -> str:
    """Recorta a frases completas sin pasar de max_chars (sin cortes a media palabra)."""
    frases = re.split(r"(?<=[.!?])\s+", texto.strip())
    out = ""
    for f in frases:
        if len(out) + len(f) + 1 > max_chars:
            break
        out = f"{out} {f}".strip()
    return out or texto[:max_chars]


def _mock_summary(title: str, body: str) -> str:
    frases = re.split(r"(?<=[.!?])\s+", body.strip())
    resumen = _truncar_frases(" ".join(frases[:2]), 280)
    palabras = re.findall(r"\b[a-záéíóúñ]{5,}\b", (title + " " + body).lower())
    stop = {"sobre", "entre", "desde", "hasta", "porque", "cuando", "aunque"}
    tags, vistos = [], set()
    for p in palabras:
        if p not in stop and p not in vistos:
            vistos.add(p)
            tags.append(p)
        if len(tags) == 4:
            break
    return json.dumps(
        {"headline": title[:70], "summary": resumen, "tags": tags},
        ensure_ascii=False,
    )


def _mock_daily(items: list[dict]) -> str:
    highlights = [it.get("headline") or it.get("title", "") for it in items[:5]]
    digest = _truncar_frases(" ".join(it.get("summary", "") for it in items[:4]), 600)
    return json.dumps(
        {
            "intro": f"Resumen del día: {len(items)} noticias publicadas.",
            "highlights": highlights,
            "digest": digest,
        },
        ensure_ascii=False,
    )


# --- API pública ------------------------------------------------------------

def summarize_article(title: str, body: str) -> dict:
    """Resume un artículo. Devuelve dict con headline, summary y tags."""
    prompt = _build_summary_prompt(title, body)
    try:
        raw = _invoke_bedrock(SYSTEM_PROMPT, prompt, max_tokens=512)
    except Exception:  # noqa: BLE001 — sin AWS/credenciales → mock
        raw = _mock_summary(title, body)
    return _parse_json(raw)


def summarize_day(items: list[dict]) -> dict:
    """Genera el resumen diario a partir de los resúmenes de cada artículo."""
    prompt = _build_daily_prompt(items)
    try:
        raw = _invoke_bedrock(SYSTEM_PROMPT, prompt, max_tokens=800)
    except Exception:  # noqa: BLE001
        raw = _mock_daily(items)
    return _parse_json(raw)


def _parse_json(raw: str) -> dict:
    """El modelo puede envolver el JSON en texto; extraemos el bloque {...}."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return {"summary": raw.strip()}
