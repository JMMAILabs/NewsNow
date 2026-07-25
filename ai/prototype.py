"""
NewsNow — Prototipo funcional del asistente de IA (ejecutable en local).

Demuestra end-to-end, sin necesidad de desplegar nada:
  1. Resumen de cada noticia individual.
  2. Generación del resumen diario a partir de esos resúmenes (map-reduce).

Uso:
    python prototype.py

Comportamiento:
  - Si hay credenciales de AWS y acceso a Bedrock (variables de entorno
    AWS_* + BEDROCK_MODEL_ID), usa el modelo real.
  - Si no, usa automáticamente el modo mock (resumen extractivo local) para
    que la demo sea reproducible en cualquier máquina.
"""

import json
import os
import sys

from bedrock_client import summarize_article, summarize_day

# La consola de Windows (cp1252) no soporta emojis/UTF-8 por defecto.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001 — entornos donde reconfigure no está disponible
    pass

# El prototipo es una demo: si Bedrock no responde, cae al mock en vez de reventar.
# (En las Lambdas de producción esto va en "false": los errores reales van a la DLQ.)
os.environ.setdefault("NEWSNOW_ALLOW_MOCK", "1")

# Noticias de ejemplo, como si acabaran de crearse en el panel de edición.
ARTICLES = [
    {
        "id": "a1",
        "category": "tecnología",
        "title": "NewsNow lanza su nueva plataforma de noticias en la nube",
        "body": (
            "El periódico digital NewsNow ha presentado hoy su nueva plataforma "
            "construida íntegramente sobre servicios en la nube. La solución "
            "utiliza una arquitectura serverless capaz de escalar automáticamente "
            "durante picos de tráfico provocados por contenido viral. Según la "
            "compañía, el objetivo es ofrecer una experiencia rápida a millones de "
            "lectores sin necesidad de gestionar servidores. La plataforma incorpora "
            "además un asistente de inteligencia artificial que resume las noticias."
        ),
    },
    {
        "id": "a2",
        "category": "economía",
        "title": "Los influencers impulsan el tráfico de los medios digitales",
        "body": (
            "Un nuevo estudio revela que los medios digitales que colaboran con "
            "influencers experimentan aumentos de tráfico de hasta el 400% en "
            "cuestión de horas. Los expertos advierten de que estas subidas "
            "repentinas exigen infraestructuras elásticas para evitar caídas del "
            "servicio. Las redacciones que apuestan por la nube consiguen absorber "
            "estos picos con mayor facilidad y menor coste operativo."
        ),
    },
    {
        "id": "a3",
        "category": "tecnología",
        "title": "La IA generativa transforma las redacciones periodísticas",
        "body": (
            "Cada vez más periódicos incorporan modelos de lenguaje para tareas de "
            "apoyo editorial, como la generación de titulares, la clasificación de "
            "contenidos y la elaboración de resúmenes automáticos. Los responsables "
            "de producto subrayan que la IA no sustituye al periodista, sino que le "
            "libera de tareas repetitivas. La clave, señalan, está en mantener la "
            "supervisión humana y la fidelidad a las fuentes."
        ),
    },
]


def _pretty(title: str, data: dict) -> None:
    print(f"\n{'─' * 70}\n{title}\n{'─' * 70}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    usa_bedrock = bool(os.environ.get("BEDROCK_MODEL_ID")) and _aws_available()
    modo = "BEDROCK real" if usa_bedrock else "MOCK local"
    print(f"\n🤖 NewsNow — Prototipo del asistente de IA   (modo: {modo})")

    # --- Paso 1: resumen de cada artículo -----------------------------------
    resumidos = []
    for art in ARTICLES:
        summary = summarize_article(art["title"], art["body"])
        resumidos.append(
            {
                "title": art["title"],
                "category": art["category"],
                "headline": summary.get("headline"),
                "summary": summary.get("summary"),
                "tags": summary.get("tags"),
            }
        )
        _pretty(f"Resumen individual — {art['id']}", resumidos[-1])

    # --- Paso 2: resumen diario (map-reduce sobre los resúmenes)
    daily = summarize_day(resumidos)
    _pretty("RESUMEN DIARIO", daily)


def _aws_available() -> bool:
    try:
        import boto3

        return boto3.session.Session().get_credentials() is not None
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    main()
