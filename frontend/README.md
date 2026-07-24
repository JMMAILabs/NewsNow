# Frontend — apps React estáticas

Dos SPAs con **Vite + React**. Son **sitios estáticos**: `npm run build` genera una
carpeta `dist/` que se sube a **S3** y se sirve por **CloudFront** (ver
[`../terraform/frontend.tf`](../terraform/frontend.tf)).

| App | Qué es |
|---|---|
| [`public-web/`](public-web/) | Web pública: portada de noticias + resumen diario. |
| [`admin-web/`](admin-web/) | Panel con **login** + **CRUD** de artículos. |

Ambas funcionan **sin backend** (fallback *mock*), para poder verlas en local. Para
conectarlas al API real, define `VITE_API_URL` (output `api_endpoint` de Terraform)
en un fichero `.env`.

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
# en cada carpeta, apuntando al API desplegado:
echo "VITE_API_URL=https://<api-id>.execute-api.eu-west-1.amazonaws.com" > .env
npm run build
aws s3 sync dist/ s3://<bucket>            # buckets en los outputs de Terraform
aws cloudfront create-invalidation --distribution-id <id> --paths "/*"
```

## Nota sobre la autenticación (admin)

En la demo el login es *mock* (cualquier credencial). En producción se sustituye por
**Amazon Cognito** (User Pool ya provisionado en `terraform/auth.tf`): login → JWT →
se envía en la cabecera `Authorization`, que el API valida con su *JWT authorizer*.
