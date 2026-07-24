# Diagrama de arquitectura — Infraestructura

> Diagrama en **Mermaid** (se renderiza directamente en GitHub/GitLab/VS Code y es
> versionable en Git). En la entrega se incluye también export a imagen.
> Se puede reconstruir en [draw.io](https://draw.io) importando este mismo grafo.

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
        SQS["SQS<br/>(cola de resúmenes)"]
        LambdaSum["Lambda<br/>resumen artículo"]
        EB["EventBridge Scheduler<br/>(cron diario)"]
        LambdaDaily["Lambda<br/>resumen diario"]
        Bedrock["Amazon Bedrock<br/>(Claude)"]
    end

    subgraph Obs["📊 Observabilidad"]
        CW["CloudWatch<br/>logs / métricas / alarmas"]
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

    DDB --> Streams --> SQS --> LambdaSum
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
```

## Flujo resumido

1. **Lectura pública (el 95 % del tráfico).** El lector llega vía Route 53 →
   CloudFront. La web React y las imágenes se sirven **desde la caché del CDN**,
   sin tocar el origen. Las llamadas a la API para leer noticias también se cachean
   en CloudFront/API Gateway. Esto es lo que absorbe los picos de influencers.

2. **Escritura (panel admin).** El editor se autentica en **Cognito**, que emite un
   JWT. El panel React llama al **API Gateway**, que valida el token y ejecuta la
   **Lambda** del backend (CRUD sobre **DynamoDB** e imágenes en **S3**).

3. **IA: resumen individual.** Al crear/editar un artículo, **DynamoDB Streams**
   emite un evento → **SQS** (buffer que amortigua los picos) → **Lambda** que llama
   a **Bedrock** y guarda el resumen en DynamoDB.

4. **IA: resumen diario.** **EventBridge Scheduler** dispara una Lambda cada día que
   recopila los artículos de la jornada, pide a **Bedrock** un digest y lo persiste.
