# Diagrama de arquitectura — Infraestructura

> Diagrama en **Mermaid** (se renderiza directamente en GitHub/GitLab/VS Code y es
> versionable en Git). La versión **draw.io** que sugiere el enunciado está en
> [`newsnow-arquitectura.drawio`](newsnow-arquitectura.drawio) → página *Infraestructura*
> (ábrela en [draw.io](https://draw.io) / diagrams.net).

```mermaid
flowchart TB
    subgraph Users["👥 Usuarios"]
        Reader["Lectores<br/>(gran volumen, picos)"]
        Editor["Editores / Redactores"]
    end

    subgraph Edge["🌍 Capa Edge (global)"]
        R53["Route 53<br/>DNS"]
        CFpub["CloudFront<br/>(web pública)"]
        CFadm["CloudFront<br/>(panel admin)"]
        WAF["AWS WAF<br/>(opcional)"]
    end

    subgraph Static["📦 Frontend estático (S3)"]
        S3pub["S3<br/>web pública React"]
        S3adm["S3<br/>panel admin React"]
        S3media["S3<br/>imágenes / media"]
    end

    subgraph Identity["🔐 Identidad"]
        Cognito["Amazon Cognito<br/>User Pool (JWT)"]
    end

    subgraph Backend["⚙️ Backend serverless"]
        APIGW["API Gateway<br/>(HTTP API)"]
        LambdaAPI["Lambda<br/>API REST (Python)"]
    end

    subgraph Data["🗄️ Datos"]
        DDB["DynamoDB<br/>(on-demand)<br/>artículos + resúmenes"]
        DAX["DAX<br/>(cache lectura, opcional)"]
        Streams["DynamoDB Streams"]
    end

    subgraph AI["🤖 Capa de IA"]
        LambdaSum["Lambda<br/>resumen artículo<br/>(concurrencia reservada)"]
        DLQ["SQS<br/>(Dead Letter Queue)"]
        EB["EventBridge Scheduler<br/>(cron diario)"]
        LambdaDaily["Lambda<br/>resumen diario"]
        Bedrock["Amazon Bedrock<br/>(Claude)"]
    end

    subgraph Obs["📊 Observabilidad"]
        CW["CloudWatch<br/>logs / métricas / alarmas"]
        SNS["SNS<br/>alertas"]
    end

    Reader --> R53
    Editor --> R53
    R53 --> CFpub
    R53 --> CFadm
    CFpub -. contenido cacheado .-> S3pub
    CFadm --> WAF --> S3adm
    CFpub --> S3media

    CFpub -->|GET noticias| APIGW
    CFadm -->|CRUD autenticado| APIGW
    Editor -->|login| Cognito
    Cognito -. valida JWT .-> APIGW

    APIGW --> LambdaAPI
    LambdaAPI --> DDB
    LambdaAPI --> DAX --> DDB
    LambdaAPI --> S3media

    DDB --> Streams --> LambdaSum
    LambdaSum -. fallo tras reintentos .-> DLQ
    LambdaSum --> Bedrock
    LambdaSum --> DDB

    EB --> LambdaDaily
    LambdaDaily --> DDB
    LambdaDaily --> Bedrock
    LambdaDaily --> DDB

    LambdaAPI -.-> CW
    LambdaSum -.-> CW
    LambdaDaily -.-> CW
    APIGW -.-> CW
    CW --> SNS
```

## Flujo resumido

1. **Lectura pública (el 95 % del tráfico).** El lector llega vía Route 53 →
   CloudFront. La web React se sirve **desde la caché del CDN**, sin tocar el origen. Y
   las lecturas de la API (`/articles`, `/daily-summary`) van por un **segundo origen
   de CloudFront con TTL corto**, así que también se responden desde el edge. Esto es lo
   que absorbe los picos de influencers.

2. **Escritura (panel admin).** El editor se autentica en **Cognito**, que emite un
   JWT. El panel React llama al **API Gateway**, que valida el token y ejecuta la
   **Lambda** del backend (CRUD sobre **DynamoDB** e imágenes en **S3**).

3. **IA: resumen individual.** Al crear/editar un artículo, **DynamoDB Streams**
   dispara directamente la **Lambda** (con *batching* y reintentos, que amortiguan los
   picos), que llama a **Bedrock** y guarda el resumen en DynamoDB. Una cola **SQS** hace
   de **DLQ** para los eventos que fallan tras reintentar.

4. **IA: resumen diario.** **EventBridge Scheduler** dispara una Lambda cada madrugada
   que recopila los artículos de la **jornada anterior** (ya completa), pide a
   **Bedrock** un digest y lo persiste.

> **Nota de alcance:** **Route 53**, **WAF** y **DAX** aparecen como *estado objetivo* de
> una arquitectura completa. El Terraform del MVP usa los **dominios por defecto de
> CloudFront** (sin Route 53), **sin WAF** y **sin DAX** (se activan cuando el tráfico o
> la seguridad lo justifiquen — ver la hoja de ruta en `01-infraestructura.md`). El resto
> de nodos del diagrama **sí** están implementados en [`../../terraform/`](../../terraform/).
