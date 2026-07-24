# NewsNow — Caso Práctico Cloud AI Engineer

[![CI](https://github.com/JMMAILabs/NewsNow/actions/workflows/ci.yml/badge.svg)](https://github.com/JMMAILabs/NewsNow/actions/workflows/ci.yml)

Solución completa al caso práctico de **NewsNow**, un MVP para servir noticias con
un panel de administración autenticado y un asistente de IA que resume noticias
individuales y genera un resumen diario.

La solución se apoya al máximo en **servicios PaaS/serverless de AWS** para minimizar
la operación y absorber los picos de tráfico esperados (contenido promocionado por
influencers).

---

## 📂 Estructura del repositorio

```
CasoPractico_Logicalis/
├── README.md                      ← Este archivo (índice general)
├── Makefile                       ← Atajos: make test / validate / run / deploy…
├── pyproject.toml                 ← Metadatos + config de ruff y pytest
├── .github/workflows/ci.yml       ← CI: ruff + pytest + terraform validate + tflint
│
├── docs/                          ← Documentación y respuestas
│   ├── 01-infraestructura.md      ← Diagrama + tráfico + automatización + prod
│   ├── 02-desarrollo-ia.md        ← Overview IA, datos, serverless, rendimiento
│   ├── 03-uso-de-ia.md            ← Cómo he usado la IA en esta prueba
│   ├── diagrams/                  ← Diagramas Mermaid + draw.io (infra + IA)
│   └── assets/                    ← Capturas (validación en PartyRock)
│
├── terraform/                     ← IaC para desplegar todo en AWS
│   ├── frontend.tf                ← S3 + CloudFront (webs React estáticas)
│   ├── auth.tf                    ← Cognito (login del panel admin)
│   ├── database.tf                ← DynamoDB (artículos + resúmenes)
│   ├── api.tf                     ← API Gateway + Lambda (backend REST)
│   ├── ai.tf                      ← Lambdas de IA + EventBridge + SQS + Bedrock
│   └── providers.tf / variables.tf / outputs.tf
│
├── backend/                       ← API REST en Python
│   ├── handler.py                 ← CRUD de artículos (Lambda)
│   └── requirements.txt
│
├── ai/                            ← Asistente de IA (prototipo funcional)
│   ├── prototype.py               ← Ejecutable en local (demo end-to-end)
│   ├── summarize_article.py       ← Lambda: resumen de un artículo
│   ├── daily_summary.py           ← Lambda: resumen diario
│   ├── bedrock_client.py          ← Cliente Bedrock (+ fallback mock)
│   └── requirements.txt
│
├── frontend/                      ← 2 apps React estáticas (Vite)
│   ├── public-web/                ← Web pública (portada + resumen diario)
│   └── admin-web/                 ← Panel admin (login + CRUD)
│
├── loadtest/                      ← Prueba de carga con k6
│
└── tests/                         ← pytest: idempotencia, batch, parseo JSON
```

---

## 🧭 Índice de respuestas al enunciado

### Infraestructura → [`docs/01-infraestructura.md`](docs/01-infraestructura.md)
1. Diagrama de arquitectura + razonamiento
2. Scripts de Terraform → carpeta [`terraform/`](terraform/)
3. Gestión de grandes volúmenes de tráfico
4. Herramientas para automatizar el despliegue

### Desarrollo de IA → [`docs/02-desarrollo-ia.md`](docs/02-desarrollo-ia.md)
1. Arquitectura general (overview)
2. Procesamiento y obtención de datos
3. Prototipo de código funcional → carpeta [`ai/`](ai/)
4. Despliegue serverless
5. Mejora del rendimiento de la IA

> 🔗 **Demo en vivo (modelo real, coste 0):** prompt de resumen validado con Claude
> sobre Amazon Bedrock en PartyRock →
> <https://partyrock.aws/u/jmm-labs/h23seNGsW/NewsNow-Editorial-Assistant>
> (capturas de ambos flujos en [`docs/assets/`](docs/assets/)).

### Uso de la IA en la prueba → [`docs/03-uso-de-ia.md`](docs/03-uso-de-ia.md)

---

## 🏗️ Resumen de la arquitectura propuesta

| Componente | Servicio AWS | Por qué |
|---|---|---|
| Web pública (React estático) | **S3 + CloudFront** | Hosting estático servido desde CDN; el edge absorbe los picos |
| Panel admin (React estático) | **S3 + CloudFront** | Mismo patrón; separado por dominio/distribución |
| Autenticación del panel | **Amazon Cognito** | PaaS de identidad; emite JWT que valida el API |
| API REST (Python) | **API Gateway (HTTP API) + Lambda** | 100% serverless, escala automático, pago por uso |
| Base de datos | **DynamoDB (on-demand)** | Serverless, latencia de milisegundos, escala sola con el tráfico |
| Media / imágenes | **S3** | Almacenamiento de objetos servido por CloudFront |
| IA (resúmenes) | **Amazon Bedrock (Claude)** | LLM gestionado; sin infraestructura de modelos |
| Orquestación IA | **Lambda + SQS + EventBridge** | Desacopla la generación de resúmenes de las peticiones de usuario |
| Observabilidad | **CloudWatch** | Logs, métricas y alarmas de todos los servicios |

> **Principio de diseño:** ningún servidor que mantener. Todo son servicios
> gestionados que escalan a cero cuando no hay tráfico y hacia arriba de forma
> elástica durante los picos.

---

## 🚀 Cómo desplegar y probar (resumen)

```bash
# Atajos (Makefile), equivalentes a los comandos de abajo:
make test        # tests (pytest)
make validate    # valida el Terraform (sin credenciales AWS)
make run         # prototipo de IA en local (modo mock si no hay AWS)

# 1. Infraestructura
cd terraform
terraform init
terraform plan  -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars

# 2. Prototipo de IA en local (sin AWS → usa el modo mock)
cd ../ai && pip install -r requirements.txt && python prototype.py

# 3. Webs React (Vite) en local
cd ../frontend/public-web && npm install && npm run dev   # http://localhost:5173
cd ../admin-web           && npm install && npm run dev   # http://localhost:5174
```

Detalles completos en cada documento de la carpeta [`docs/`](docs/).
