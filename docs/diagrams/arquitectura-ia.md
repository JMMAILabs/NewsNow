# Diagrama de arquitectura — Asistente de IA

> Detalle del subsistema de IA (resumen individual + resumen diario).
>
> Versión **draw.io** en [`newsnow-arquitectura.drawio`](newsnow-arquitectura.drawio) →
> página *Flujo de IA*.

## 1. Resumen de un artículo individual (event-driven)

```mermaid
sequenceDiagram
    participant Editor
    participant API as API Gateway + Lambda
    participant DDB as DynamoDB
    participant Stream as DynamoDB Streams
    participant L as Lambda summarize
    participant DLQ as SQS (DLQ)
    participant BR as Bedrock (Claude)

    Editor->>API: POST/PUT artículo
    API->>DDB: guarda artículo (status=DRAFT)
    DDB->>Stream: evento INSERT/MODIFY (SK=META)
    Stream->>L: dispara (batch, con reintentos)
    L->>DDB: lee texto del artículo
    L->>BR: prompt de resumen (concurrencia reservada)
    BR-->>L: resumen + titular + tags
    L->>DDB: guarda summary (status=READY)
    L-->>DLQ: si falla tras reintentar → DLQ
```

**Por qué event-driven y no síncrono:** el editor no espera al LLM. El resumen se
genera en segundo plano y el artículo pasa de `DRAFT` a `READY` cuando está listo.
**DynamoDB Streams dispara la Lambda directamente** (con *batching* y reintentos, que
ya amortiguan las ráfagas de carga masiva); una cola **SQS** hace de *dead letter
queue* para los eventos que fallan tras reintentar. Una **concurrencia reservada**
limita las llamadas simultáneas a Bedrock para no provocar *throttling* en un pico.

## 2. Resumen diario (batch programado)

```mermaid
sequenceDiagram
    participant EB as EventBridge Scheduler
    participant L as Lambda daily-summary
    participant DDB as DynamoDB
    participant BR as Bedrock (Claude)

    EB->>L: cron diario (p.ej. 06:00 UTC)
    L->>DDB: query GSI por fecha (fan-in sobre shards, paginado)
    L->>DDB: BatchGetItem de los resúmenes (evita N+1)
    L->>BR: prompt map-reduce (por lotes si hay muchos)
    BR-->>L: digest diario estructurado
    L->>DDB: guarda DAILY#YYYY-MM-DD
```

**Estrategia map-reduce jerárquica:** en lugar de mandar todos los artículos completos
(que excederían la ventana de contexto y serían caros), se usan los **resúmenes ya
generados** de cada artículo (paso 1) y se pide a Bedrock un *resumen de resúmenes*. Si
un día trae muchos, se reduce **por lotes** y los digests parciales se combinan en una
ronda posterior, de modo que **ninguna llamada desborda el contexto**. Los resúmenes se
leen con **BatchGetItem** (no un `GetItem` por artículo) para no agotar el tiempo de la
Lambda a gran volumen.

## 3. Modelo de datos en DynamoDB (single-table)

| PK | SK | Atributos |
|---|---|---|
| `ARTICLE#<id>` | `META` | title, body, author, category, status, created_at |
| `ARTICLE#<id>` | `SUMMARY` | summary, headline, tags, model, tokens |
| `DAILY#<date>` | `SUMMARY` | digest, article_ids, created_at |

- **GSI1** (`GSI1PK = DATE#<yyyy-mm-dd>#<shard>`, `GSI1SK = created_at`) para consultar
  los artículos publicados en un día → alimenta el resumen diario y la portada. La
  clave incluye un **shard** (0–9) para repartir la escritura y evitar una *hot
  partition* bajo picos; las lecturas hacen *fan-in* sobre todos los shards.
