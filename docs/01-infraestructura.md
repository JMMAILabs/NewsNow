# Infraestructura

> Premisas del enunciado: máxima dependencia de **PaaS**, proveedor **AWS**, se
> esperan **grandes picos de tráfico** (influencers), y para simplificar asumimos
> **redes abiertas** sin políticas de acceso.

---

## 1. Diagrama de arquitectura y razonamiento

📊 **Diagrama:** [`diagrams/arquitectura-infra.md`](diagrams/arquitectura-infra.md) (Mermaid) · [`diagrams/newsnow-arquitectura.drawio`](diagrams/newsnow-arquitectura.drawio) (**draw.io**, el del enunciado)

### Los tres componentes del enunciado y su mapeo a AWS

| Componente pedido | Servicio AWS |
|---|---|
| Web pública React (sitio estático) | **S3 + CloudFront** |
| API REST en Python (backend) | **API Gateway (HTTP API) + Lambda** |
| Panel admin React con autenticación (CRUD) | **S3 + CloudFront + Cognito** |
| Persistencia de datos | **DynamoDB** |

### Razonamiento (por qué esta solución)

**a) Frontend estático → S3 + CloudFront.**
Las dos apps de React son sitios estáticos (HTML/JS/CSS). El patrón canónico y más
barato en AWS es alojarlas en **S3** y servirlas por **CloudFront** (CDN global).
- CloudFront **cachea el contenido en el edge**, cerca del usuario: baja latencia y,
  sobre todo, **absorbe los picos** sin tocar el origen. Este es el punto clave para
  el tráfico de influencers.
- No hay servidores web que mantener ni escalar. Es PaaS puro.
- Las dos webs se despliegan como **distribuciones separadas** (dominios distintos,
  p. ej. `www.newsnow.com` y `admin.newsnow.com`) para aislar caché, seguridad y
  ciclo de vida.

**b) Backend → API Gateway + Lambda (Python).**
El enunciado pide una API REST en Python. En clave 100 % serverless:
- **AWS Lambda** ejecuta el código Python sin servidores; **escala automáticamente**
  de 0 a miles de ejecuciones concurrentes y se paga solo por invocación.
- **API Gateway (HTTP API)** expone la REST, gestiona rutas, throttling y validación
  de los JWT de Cognito.
- Alternativa considerada: **AWS App Runner** o **ECS Fargate** si el equipo
  prefiere empaquetar la API como contenedor de larga vida (Flask/FastAPI). Para un
  MVP con tráfico irregular, Lambda gana en coste (escala a cero) y simplicidad. Lo
  comento en el apartado de trade-offs.

**c) Autenticación → Amazon Cognito.**
El panel admin requiere login. **Cognito** es el servicio de identidad gestionado de
AWS: gestiona usuarios, contraseñas, MFA y emite **JWT** estándar. API Gateway valida
esos tokens de forma nativa (JWT authorizer), sin escribir lógica de auth propia.

**d) Base de datos → DynamoDB (on-demand).**
- Base de datos **serverless**: no hay instancias que dimensionar; en modo
  **on-demand** escala la capacidad automáticamente con el tráfico y cobra por
  petición. Encaja perfecto con picos impredecibles.
- Latencia de milisegundos y alta disponibilidad multi-AZ por defecto.
- El modelo de datos (artículos, resúmenes) es sencillo y de acceso por clave →
  ideal para un diseño **single-table** de DynamoDB.
- Alternativa considerada: **Aurora Serverless v2** (PostgreSQL) si se necesitaran
  consultas relacionales complejas. Para el MVP no hace falta y añade coste base;
  DynamoDB es más "serverless de verdad" (escala a cero).

**e) Media → S3.** Las imágenes de los artículos se almacenan en un bucket S3 privado
(la Lambda conoce su nombre). **Servirlas por CloudFront es una mejora de producción**
que no se ha cableado en el MVP (el foco es el flujo de artículos + IA).

**f) Observabilidad → CloudWatch.** Logs, métricas y alarmas de todos los servicios
gestionados de forma centralizada.

### Trade-offs principales

| Decisión | Alternativa | Por qué elijo la primera |
|---|---|---|
| Lambda + API GW | App Runner / Fargate | Escala a cero, coste por uso, cero gestión de instancias en un MVP |
| DynamoDB | Aurora Serverless | Serverless real, sin capacidad que planificar, precio por petición |
| Cognito | Auth0 / propio | Nativo de AWS, integración directa con API Gateway, sin coste extra de terceros |
| CloudFront | Balanceador + EC2 | El CDN cachea en el edge y elimina el cuello de botella en origen |

---

## 2. Terraform

📁 **Código:** carpeta [`../terraform/`](../terraform/)

Se ha implementado la infraestructura como código con Terraform, organizada por
dominio funcional:

| Fichero | Recursos |
|---|---|
| `providers.tf` | Provider AWS, versión, backend de estado |
| `variables.tf` | Variables parametrizables (región, nombre de proyecto, entorno…) |
| `frontend.tf` | 3 buckets S3 (web pública, admin, media) + 2 distribuciones CloudFront + OAC + **caché de edge del API** |
| `auth.tf` | Cognito User Pool + App Client + dominio hosted UI |
| `database.tf` | Tabla DynamoDB (on-demand) + GSI + Streams |
| `api.tf` | API Gateway HTTP API + Lambda del backend + rutas + JWT authorizer + access logs |
| `ai.tf` | Lambdas de IA + DLQ (SQS) + EventBridge Scheduler + permisos Bedrock |
| `observability.tf` | SNS + alarmas de CloudWatch (errores Lambda, DLQ, 5xx del API) |
| `outputs.tf` | URLs de CloudFront, endpoint del API, IDs de Cognito, etc. |

Se asumen **redes abiertas**. Los IAM roles incluidos son los
mínimos para que los servicios funcionen, no un hardening de producción.

Despliegue:
```bash
cd terraform
terraform init
terraform plan  -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

---

## 3. ¿Cómo maneja el sistema los grandes volúmenes de tráfico?

La clave es que **casi todo el tráfico es de lectura de contenido estático**, y ese
camino nunca toca un servidor. Estrategia por capas:

**a) Caché en el edge (implementada).**
CloudFront sirve la web pública desde cientos de puntos de presencia. En un pico de
influencer, miles de lectores reciben la misma copia **cacheada** sin llegar al
origen. Y **no solo el HTML**: la distribución pública lleva un **segundo origen (el
API)** con *cache behaviors* para `/articles*` y `/daily-summary*` y un **TTL corto
(30–60 s)** — así las lecturas públicas del API también se responden desde el edge y
el backend recibe **una fracción mínima** de las peticiones. Está cableado en
[`../terraform/frontend.tf`](../terraform/frontend.tf) (`aws_cloudfront_cache_policy.api_short`).

**b) Cómputo elástico y sin servidores.**
- **Lambda** escala automáticamente la concurrencia. Para latencia predecible en
  picos se puede activar **provisioned concurrency**. En sentido inverso, la Lambda de
  IA lleva **concurrencia reservada** (tope) para no saturar Bedrock en un pico.
- **API Gateway** tiene throttling configurable para proteger el backend y escala de
  forma transparente.

**c) Datos que escalan solos (y sin *hot partition*).**
- **DynamoDB on-demand** absorbe subidas bruscas de RPS sin planificar capacidad.
  Para lecturas muy intensas se añade **DAX** (caché en memoria, microsegundos).
- **Reparto por shards en el GSI por fecha.** Si todos los artículos del día
  compartieran la misma clave de partición (`DATE#hoy`), un pico concentraría lecturas
  y escrituras en **una sola partición** (throttling). Por eso la clave es
  `DATE#<fecha>#<shard>` (10 shards) y las lecturas hacen *fan-in* sobre todos. Así se
  distribuye la carga y se evita el anti-patrón de *hot key*.

**d) Desacople asíncrono.**
La generación de resúmenes (IA) **no va en la ruta de la petición del usuario**: la
dispara **DynamoDB Streams → Lambda** (con *batching* y reintentos, que ya amortiguan
las ráfagas) y **SQS actúa como Dead Letter Queue** de los eventos que fallan. Un pico
de creación de artículos se procesa a su ritmo, sin degradar la lectura ni saturar
Bedrock (concurrencia reservada + reintentos adaptativos).

**e) Alta disponibilidad por defecto.**
Todos los servicios usados (S3, CloudFront, DynamoDB, Lambda, API Gateway) son
**multi-AZ y regionales gestionados por AWS**; no hay un único punto de fallo que
mantener.

**f) Resiliencia.** Reintentos + *Dead Letter Queues*, y **alarmas de CloudWatch**
(errores de Lambda, profundidad de la DLQ, 5xx del API) → **SNS**, cableadas en
[`../terraform/observability.tf`](../terraform/observability.tf) para reaccionar antes
de que degrade.

> En resumen: **el contenido se sirve desde el CDN, el cómputo es elástico y de pago
> por uso, la base de datos escala sola y el trabajo pesado se desacopla en colas.**
> El sistema pasa de 10 a 100.000 lectores sin intervención manual.

---

## 4. Herramientas para automatizar el despliegue

**a) Infraestructura como código con Terraform.**
Todo el despliegue está descrito de forma declarativa y versionada (carpeta
`terraform/`). Ventajas: reproducible, revisable en PR, `terraform plan` muestra el
diff antes de aplicar. El **estado** se guarda remoto en un bucket **S3 + bloqueo con
DynamoDB** (o **Terraform Cloud**) para trabajo en equipo.

**b) CI/CD con pipeline automatizado.**
Recomiendo **GitHub Actions** (o GitLab CI / AWS CodePipeline según dónde viva el
código) con este flujo:

```
push / PR
   │
   ├─ lint + tests (Python, terraform validate, tflint)
   │
   ├─ terraform plan  ──►  comentario automático en el PR con el diff
   │
   └─ (al hacer merge a main)
        ├─ terraform apply           ← infraestructura
        ├─ build de las apps React   ← npm run build
        ├─ aws s3 sync ... a los buckets
        └─ cloudfront create-invalidation  ← purga la caché del CDN
```

> ✅ **Implementado** en [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml): los jobs
> de `ruff` + `pytest` + `terraform fmt/validate/tflint` corren **sin credenciales AWS**
> (validate usa `-backend=false`); el `terraform plan` real es un job **opcional** *gated*
> por OIDC. Los comandos están centralizados en un [`../Makefile`](../Makefile).

**c) Herramientas complementarias.**
- **Autenticación en AWS desde CI:** OIDC de GitHub Actions → rol IAM (sin claves
  estáticas).
- **Calidad de IaC:** `terraform fmt`, `terraform validate`, **tflint**, **Checkov**
  o **tfsec** (escaneo de seguridad).
- **Empaquetado de Lambdas:** en el propio pipeline (zip / imagen de contenedor).
- **Multi-entorno:** *workspaces* de Terraform o carpetas por entorno
  (`dev` / `staging` / `prod`) con sus `tfvars`.
- **Alternativas de IaC** si el equipo lo prefiere: **AWS CDK** (Python/TypeScript) o
  **AWS SAM/Serverless Framework** para la parte Lambda. Elijo **Terraform** por ser
  agnóstico de nube, maduro y estándar del mercado.

> **Resumen:** Terraform describe la infraestructura, un pipeline de CI/CD la aplica
> y despliega el frontend automáticamente en cada merge, e invalida la caché de
> CloudFront. Cero pasos manuales.

---

## 5. Camino a producción: seguridad, resiliencia y FinOps

El enunciado pide **redes abiertas, sin políticas de acceso**, así que el *hardening*
completo queda fuera de alcance a propósito. Aun así, se han incorporado varias
mejoras de bajo coste, y el resto se deja como **hoja de ruta consciente**.

### Ya incorporado en esta entrega

| Dimensión | Qué se ha hecho |
|---|---|
| **Seguridad** | *Least privilege*: se quitó `dynamodb:Scan` (no se usa) y se deja anotado atar `bedrock:InvokeModel` al ARN del modelo. Buckets S3 **privados** (`public_access_block`) + **cifrado SSE**. Escritura protegida por **JWT de Cognito**. **Validación de tamaño** del cuerpo (evita 500 opacos) y **500 sin fuga de detalle** al cliente. |
| **Resiliencia** | **Partial batch failures** (`ReportBatchItemFailures`) al consumir Streams. **DLQ + reintentos** en la Lambda de resumen y en el Scheduler. **PITR** en DynamoDB. **Concurrencia reservada** + **reintentos adaptativos** contra el *throttling* de Bedrock. **Alarmas CloudWatch → SNS** (errores, DLQ, 5xx). **Sin *hot partition*** (sharding del GSI). **Reduce jerárquico** en el boletín (no desborda el contexto a gran volumen). |
| **Escalabilidad** | **Caché de edge del API** en CloudFront (TTL corto) para lecturas públicas. **BatchGetItem** en el boletín (en vez de N+1). |
| **FinOps** | Lambdas en **ARM64/Graviton** (~20% más baratas). **Retención de logs** (14 días). **DynamoDB on-demand** para tráfico *spiky*. **Haiku** por defecto + **map-reduce**. **Tags** de coste. |
| **Calidad** | **Tests** (pytest) de idempotencia/batch/parseo/*prompt injection*. **CI** con ruff + pytest + terraform validate + tflint + `npm audit`. |

### Hoja de ruta (producción)

- **Seguridad:** WAF en CloudFront; *security headers* + TLS mínimo; CORS restringido a
  dominios reales; MFA + *advanced security* en Cognito; **KMS CMK** en S3/DynamoDB;
  escaneo de IaC (**Checkov/tfsec**) en el CI; secretos en Secrets Manager si aparecen.
- **Resiliencia:** **DAX** si las lecturas aprietan; multi-región/DR según el RTO/RPO
  objetivo; *canary*/blue-green en los despliegues de Lambda. *(Alarmas SNS y
  retry/backoff de Bedrock ya están incorporados arriba.)*
- **FinOps:** **AWS Budgets** con alertas; **TTL** en DynamoDB para autoexpirar contenido
  viejo; **Lambda Power Tuning** para dimensionar memoria; si el tráfico se vuelve
  **predecible y alto**, comparar DynamoDB *provisioned + autoscaling* frente a on-demand.
- **Escalabilidad (validación real):** **pruebas de carga** (k6 / Locust / Artillery)
  contra el API desplegado + dashboards de CloudWatch. El autoscaling **no se prueba con
  unit tests**: estos verifican las propiedades que lo *habilitan* (idempotencia,
  *statelessness*, manejo de batch); la escala real se mide con carga.
