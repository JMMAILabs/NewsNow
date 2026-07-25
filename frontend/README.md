# Frontend — apps React estáticas

Dos SPAs con **Vite + React**. Son **sitios estáticos**: `npm run build` genera una
carpeta `dist/` que se sube a **S3** y se sirve por **CloudFront** (ver
[`../terraform/frontend.tf`](../terraform/frontend.tf)).

| App | Qué es |
|---|---|
| [`public-web/`](public-web/) | Web pública: portada de noticias + resumen diario. |
| [`admin-web/`](admin-web/) | Panel con **login** + **CRUD** de artículos. |

Ambas funcionan **sin backend** (fallback *mock*), para poder verlas en local.

- **Web pública:** en producción se despliega en la **misma distribución de CloudFront**
  que sirve el HTML, así que llama al API por el **mismo origen** (`/articles`,
  `/daily-summary`) → CloudFront cachea esas lecturas en el edge. Por eso su build de
  producción va **sin `VITE_API_URL`** (ver [`public-web/.env.example`](public-web/.env.example)).
  El *fallback* a datos de ejemplo es **solo de desarrollo**: si el API falla en
  producción, la web muestra un **estado de error**, nunca noticias inventadas.
- **Panel admin:** su distribución no cachea el API; usa `VITE_API_URL` (output
  `api_endpoint` de Terraform) para llamar a API Gateway con el JWT.

## Ejecutar en local

```bash
cd frontend/public-web      # o frontend/admin-web
npm install
npm run dev                 # pública → http://localhost:5173 · admin → http://localhost:5174
```

## Build de producción

```bash
npm run build               # genera dist/
npm run preview             # sirve dist/ en local para revisarlo
```

## Despliegue (tras `terraform apply`)

```bash
# WEB PÚBLICA — mismo origen (sin VITE_API_URL): CloudFront cachea las lecturas.
cd public-web
npm run build
aws s3 sync dist/ s3://<bucket-public-web>          # buckets en los outputs de Terraform
aws cloudfront create-invalidation --distribution-id <id-public> --paths "/*"

# PANEL ADMIN — apunta al API Gateway (con JWT; sin caché).
cd ../admin-web
echo "VITE_API_URL=https://<api-id>.execute-api.eu-west-1.amazonaws.com" > .env
npm run build
aws s3 sync dist/ s3://<bucket-admin-web>
aws cloudfront create-invalidation --distribution-id <id-admin> --paths "/*"
```

## Nota sobre la autenticación (admin)

En la demo el login es *mock* (cualquier credencial). En producción se sustituye por
**Amazon Cognito** (User Pool ya provisionado en `terraform/auth.tf`): login → JWT →
se envía en la cabecera `Authorization`, que el API valida con su *JWT authorizer*.

> ⚠️ **Contra el API real:** la web pública (solo lectura) funciona apuntando
> `VITE_API_URL` al API desplegado. El panel admin, en cambio, envía un token *mock*
> que el *JWT authorizer* de Cognito **rechazaría (401)** en las escrituras — cablear
> el login real de Cognito es el paso de producción pendiente.
