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

**e) Media → S3.** Las imágenes de los artículos van a un bucket S3 servido por
CloudFront, igual que el resto de estáticos.

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
| `frontend.tf` | 3 buckets S3 (web pública, admin, media) + 2 distribuciones CloudFront + OAC |
| `auth.tf` | Cognito User Pool + App Client + dominio hosted UI |
| `database.tf` | Tabla DynamoDB (on-demand) + GSI + Streams |
| `api.tf` | API Gateway HTTP API + Lambda del backend + rutas + JWT authorizer |
| `ai.tf` | Lambdas de IA + SQS + DLQ + EventBridge Scheduler + permisos Bedrock |
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

**a) Caché en el edge.**
CloudFront sirve la web pública y las imágenes desde cientos de puntos de presencia.
En un pico de influencer, miles de lectores reciben la misma copia **cacheada** sin
llegar al origen. Se cachea también la respuesta del API para las noticias públicas
(con un TTL corto, ej: 30–60s) → el backend recibe una fracción mínima de las peticiones.

**b) Cómputo elástico y sin servidores.**
- **Lambda** escala automáticamente la concurrencia. Para latencia predecible en
  picos se puede activar **provisioned concurrency** o **autoscaling** de la misma.
- **API Gateway** tiene throttling configurable para proteger el backend y escala de
  forma transparente.

**c) Datos que escalan solos.**
- **DynamoDB on-demand** absorbe subidas bruscas de RPS sin planificar capacidad.
  Para lecturas muy intensas se añade **DAX** (caché en memoria, microsegundos).
- Modelo de acceso por clave → sin *joins*.

**d) Desacople asíncrono.**
La generación de resúmenes (IA) va por **SQS + Lambda**, no en la ruta de la petición
del usuario. Un pico de creación de artículos se **encola y se procesa a su ritmo**,
sin degradar la experiencia de lectura ni saturar Bedrock.

**e) Alta disponibilidad por defecto.**
Todos los servicios usados (S3, CloudFront, DynamoDB, Lambda, API Gateway) son
**multi-AZ y regionales gestionados por AWS**; no hay un único punto de fallo que
mantener.

**f) Resiliencia.** Reintentos + *Dead Letter Queues* en las colas, y alarmas de
CloudWatch sobre errores/latencia/throttling para reaccionar antes de que degrade.

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
| **Seguridad** | *Least privilege*: se quitó `dynamodb:Scan` (no se usa) y se deja anotado atar `bedrock:InvokeModel` al ARN del modelo. Buckets S3 **privados** (`public_access_block`) + **cifrado SSE**. Escritura protegida por **JWT de Cognito**. |
| **Resiliencia** | **Partial batch failures** (`ReportBatchItemFailures`) al consumir Streams: un registro malo no reprocesa el batch. **DLQ + reintentos** en la Lambda de resumen y en el Scheduler diario. **PITR** en DynamoDB. |
| **FinOps** | Lambdas en **ARM64/Graviton** (~20% más baratas). **Retención de logs** (14 días) para que no crezcan sin fin. **DynamoDB on-demand** para tráfico *spiky*. **Haiku** por defecto + **map-reduce**. **Tags** de coste. |
| **Calidad** | **Tests** (pytest) de idempotencia/batch/parseo. **CI** con ruff + pytest + terraform validate + tflint. |

### Hoja de ruta (producción)

- **Seguridad:** WAF en CloudFront; *security headers* + TLS mínimo; CORS restringido a
  dominios reales; MFA + *advanced security* en Cognito; **KMS CMK** en S3/DynamoDB;
  escaneo de IaC (**Checkov/tfsec**) en el CI; secretos en Secrets Manager si aparecen.
- **Resiliencia:** **alarmas CloudWatch** (errores, throttles, profundidad de DLQ) → SNS;
  **retry/backoff** en el cliente de Bedrock ante *throttling*; **DAX** si las lecturas
  aprietan; multi-región/DR según el RTO/RPO objetivo.
- **FinOps:** **AWS Budgets** con alertas; **TTL** en DynamoDB para autoexpirar contenido
  viejo; **Lambda Power Tuning** para dimensionar memoria; si el tráfico se vuelve
  **predecible y alto**, comparar DynamoDB *provisioned + autoscaling* frente a on-demand.
- **Escalabilidad (validación real):** **pruebas de carga** (k6 / Locust / Artillery)
  contra el API desplegado + dashboards de CloudWatch. El autoscaling **no se prueba con
  unit tests**: estos verifican las propiedades que lo *habilitan* (idempotencia,
  *statelessness*, manejo de batch); la escala real se mide con carga.
