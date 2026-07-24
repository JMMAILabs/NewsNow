# Desarrollo de IA

> NewsNow quiere un asistente que **resuma noticias individuales** y genere un
> **resumen diario**.

---

## 1. Arquitectura general (overview)

📊 **Diagrama detallado:** [`diagrams/arquitectura-ia.md`](diagrams/arquitectura-ia.md)

El asistente se apoya en **Amazon Bedrock** (modelos Claude) como motor de LLM
gestionado, y en dos flujos serverless desacoplados:

```
┌─────────────────────────────────────────────────────────────────────┐
│  FLUJO A — Resumen individual (event-driven, en tiempo casi real)     │
│                                                                       │
│  Editor crea/edita artículo → DynamoDB → Streams → (SQS) → Lambda    │
│  → Bedrock (Claude) → guarda resumen + tags → artículo pasa a READY   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  FLUJO B — Resumen diario (batch programado)                          │
│                                                                       │
│  EventBridge Scheduler (cron diario) → Lambda → lee los resúmenes     │
│  del día (GSI por fecha) → Bedrock (map-reduce) → guarda el boletín   │
└─────────────────────────────────────────────────────────────────────┘
```

**Decisiones de diseño:**

- **Bedrock en lugar de auto-hospedar un modelo.** Es un servicio gestionado
  (PaaS), sin GPUs que operar, con varios modelos disponibles y facturación por
  token. Coherente con la estrategia "máximo PaaS" del enunciado.
- **Event-driven para el resumen individual.** El editor no espera al LLM: guarda
  el artículo y el resumen se genera en segundo plano. Se usa **DynamoDB Streams**
  como disparador y una **cola (SQS)** como amortiguador ante ráfagas + reintentos
  con *dead letter queue*.
- **Map-reduce para el resumen diario.** Se reutilizan los resúmenes
  ya generados en el Flujo A y se pide a Bedrock un *resumen de resúmenes*. Es la
  técnica estándar para resumir grandes volúmenes de documentos.
- **Modelo por defecto: Claude 4.5 Haiku.** Rápido y económico, suficiente para
  resúmenes de gran volumen. Parametrizable (`bedrock_model_id`) para subir a un
  modelo más potente si se necesita más calidad.

---

## 2. ¿Cómo procesar y obtener los datos?

### Obtención (ingesta)

Los datos **nacen en el propio sistema**: los editores crean los artículos desde el
panel admin → API → **DynamoDB**. No dependemos de scraping externo. Cada artículo
es la **fuente de la verdad** y ya contiene el texto a resumir.

Para el resumen diario, la obtención es una **consulta por fecha** al GSI de
DynamoDB (`GSI1PK = DATE#yyyy-mm-dd`), que devuelve los artículos de la jornada.


### Procesamiento (pipeline de resumen)

1. **Extracción y limpieza:** se toma `title` + `body`. Se eliminaría HTML/ruido si
   el cuerpo viniera enriquecido (en el MVP es texto plano).
2. **Control de tamaño:** si un artículo excede la ventana de contexto, se
   **fragmenta (chunking)** y se resume por partes (map) antes de combinar (reduce).
   Para noticias normales no hace falta.
3. **Prompt engineering:** un *system prompt* fija el rol (asistente editorial),
   el idioma, el tono neutral y la **fidelidad a la fuente**. El *user
   prompt* pide una **salida estructurada en JSON** (`headline`, `summary`, `tags`)
   para poder guardarla y renderizarla directamente.
4. **Parámetros del modelo:** `temperature` baja (0.2) para resúmenes fieles y
   estables; `max_tokens` acotado para controlar coste y longitud.
5. **Post-proceso:** se parsea el JSON (con extracción defensiva por si el modelo lo
   envuelve en texto) y se persiste el resumen en DynamoDB (`SK = SUMMARY`).
6. **Resumen diario (map-reduce):** se agregan los resúmenes del día y se pide un
   digest con introducción, titulares destacados y párrafo de síntesis.

Todo esto está implementado en [`../ai/bedrock_client.py`](../ai/bedrock_client.py).

---

## 3. Prototipo de código funcional

📁 **Código:** carpeta [`../ai/`](../ai/)

- [`prototype.py`](../ai/prototype.py) — **demo ejecutable end-to-end en local**.
  Resume 3 noticias de ejemplo y genera el resumen diario.
- [`bedrock_client.py`](../ai/bedrock_client.py) — cliente de Bedrock (Claude) con
  *prompts*, control de parámetros y parseo de salida. Incluye **fallback mock**
  (resumen extractivo) para ejecutarse **sin credenciales AWS**.
- [`summarize_article.py`](../ai/summarize_article.py) — Lambda del Flujo A.
- [`daily_summary.py`](../ai/daily_summary.py) — Lambda del Flujo B.

Ejecutar:
```bash
cd ai
pip install -r requirements.txt
python prototype.py
```

Salida (modo mock, reproducible en cualquier máquina):
```
🤖 NewsNow — Prototipo del asistente de IA   (modo: MOCK local)
📰 Resumen individual — a1 { "headline": ..., "summary": ..., "tags": [...] }
📰 Resumen individual — a2 { ... }
📰 Resumen individual — a3 { ... }
🗞️  RESUMEN DIARIO { "intro": ..., "highlights": [...], "digest": ... }
```

Contra Bedrock real basta con exportar `AWS_REGION` + `BEDROCK_MODEL_ID` y tener
credenciales con acceso al modelo.

### Validación con modelo real (PartyRock)

Además de la demo local en modo mock, el prompt se ha validado con **Claude Sonnet
4.6 sobre Amazon Bedrock** usando **PartyRock** (el *playground* no-code de Bedrock,
coste 0). Con la noticia de ejemplo y temperatura 0, el modelo devolvió el JSON
esperado de forma limpia y fiel al texto, en los **dos flujos** de la arquitectura:

| Flujo | Widget | Salida | Captura |
|---|---|---|---|
| A — resumen individual | *Resumen editorial* | `headline`, `summary`, `tags` | [ver](assets/partyrock-flujo-a-resumen-individual.png) |
| B — resumen diario (*map-reduce*) | *Boletín diario NewsNow* | `intro`, `highlights`, `digest` | [ver](assets/partyrock-flujo-b-resumen-diario.png) |

🔗 **App pública:** <https://partyrock.aws/u/jmm-labs/h23seNGsW/NewsNow-Editorial-Assistant>

> PartyRock valida el *prompt* y la calidad del modelo; **no sustituye** la
> integración programática vía `InvokeModel` ni el despliegue serverless (Lambda +
> Bedrock), que son los que aparecen en el código y el Terraform. En la demo usé
> Sonnet 4.6 (calidad techo); el modelo **por defecto en el código es Haiku** por
> coste/velocidad para gran volumen (ver el apartado 5 de este documento,
> "Selección de modelo por tarea").

---

## 4. ¿Se puede desplegar en un sistema serverless?

**Sí, de hecho el diseño es serverless de principio a fin.** El mismo código del
prototipo se despliega tal cual:

| Pieza del prototipo | Recurso serverless | Trigger |
|---|---|---|
| `summarize_article.lambda_handler` | **AWS Lambda** | **DynamoDB Streams** (al crear/editar) |
| `daily_summary.lambda_handler` | **AWS Lambda** | **EventBridge Scheduler** (cron diario) |
| `bedrock_client` (LLM) | **Amazon Bedrock** | invocado por las Lambdas |
| Persistencia | **DynamoDB** | — |
| Amortiguación / reintentos | **SQS + DLQ** | — |

Ya está **provisionado con Terraform** en
[`../terraform/ai.tf`](../terraform/ai.tf): empaqueta el código de la carpeta `ai/`,
crea las dos Lambdas, el *event source mapping* del stream (con filtro y DLQ) y el
*schedule* de EventBridge, más los permisos IAM para invocar Bedrock.

Ventajas de este enfoque serverless:
- **Escala a cero** cuando no hay artículos; escala solo en picos de publicación.
- **Pago por uso**: solo se paga por invocación de Lambda y por token de Bedrock.
- **Sin operación**: nada de servidores, colas o modelos que mantener.

---

## 5. ¿Cómo mejorar el rendimiento de la IA?

Distingo **rendimiento = calidad**, **latencia/throughput** y **coste**.

### Calidad de los resúmenes
- **Prompt engineering** iterado + *few-shot* con ejemplos del estilo editorial de
  NewsNow.
- **Salida estructurada / JSON mode** para respuestas fiables y parseables.
- **Selección de modelo por tarea**: Haiku para el grueso; un modelo mayor (Opus/Fable)
  para portada o temas sensibles.
- **RAG / contexto**: enriquecer el resumen con artículos relacionados (embeddings +
  búsqueda vectorial) para dar contexto y evitar repeticiones.
- **Evaluación continua**: *golden set* de noticias con resúmenes de referencia y
  métricas (ROUGE, o *LLM-as-a-judge*) para detectar regresiones al cambiar prompts.
- **Guardrails**: verificación de fidelidad (que no invente cifras/nombres) y
  filtros de contenido de Bedrock Guardrails.

### Latencia y throughput
- **Modelo más pequeño/rápido** (Haiku) para el camino online.
- **Prompt caching** para reutilizar el system prompt y reducir tokens/latencia.
- **Streaming** de la respuesta si se muestra en vivo al editor.
- **Procesamiento asíncrono y por lotes** (ya en el diseño con SQS): agrupar
  artículos y usar **Bedrock Batch Inference** para grandes volúmenes con menor coste.
- **Concurrencia de Lambda** (provisioned) para absorber ráfagas sin arranque en frío.

### Coste
- Usar el **modelo más barato que cumpla la calidad** y subir de nivel solo cuando
  haga falta.
- **Map-reduce** en el resumen diario (resumir resúmenes, no textos completos).
- **Cachear** resúmenes y no regenerarlos si el artículo no cambió (hash del cuerpo).
- **Acotar `max_tokens`** de entrada y salida.
- **Batch inference** para trabajos no urgentes (hasta ~50% más barato).

> En una frase: **modelo adecuado a cada tarea, prompts estructurados y evaluados,
> procesamiento asíncrono/por lotes, caching y map-reduce.** Así se mejora calidad,
> latencia y coste a la vez.
