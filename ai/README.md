# Asistente de IA — Prototipo

Prototipo funcional del asistente de NewsNow que:
1. **Resume noticias individuales**.
2. **Genera un resumen diario** (boletín) a partir de esos resúmenes.

## Ficheros

| Fichero | Rol |
|---|---|
| `prototype.py` | Demo ejecutable end-to-end en local |
| `bedrock_client.py` | Cliente de Bedrock (Claude) + fallback mock sin AWS |
| `summarize_article.py` | Lambda: resumen de 1 artículo (trigger DynamoDB Streams) |
| `daily_summary.py` | Lambda: resumen diario (trigger EventBridge Scheduler) |
| `requirements.txt` | Dependencias (`boto3`) |

## Ejecutar la demo (sin AWS)

```bash
cd ai
pip install -r requirements.txt
python prototype.py
```

Si **no** hay credenciales de AWS, el prototipo usa automáticamente el **modo
mock** (resumen extractivo local) para que la demo sea reproducible en cualquier
máquina. Verás los resúmenes individuales y el resumen diario impresos por consola.

## Ejecutar contra Bedrock real

```bash
export AWS_REGION=eu-west-1
export BEDROCK_MODEL_ID=anthropic.claude-haiku-4-5
# requiere credenciales AWS con acceso al modelo habilitado en Bedrock
python prototype.py
```

## Cómo encaja en producción

- `summarize_article.lambda_handler` se despliega como la Lambda que **DynamoDB
  Streams** dispara al crear/editar un artículo.
- `daily_summary.lambda_handler` se despliega como la Lambda que **EventBridge
  Scheduler** ejecuta cada día.
- Ambas se empaquetan con Terraform (`terraform/ai.tf`).
