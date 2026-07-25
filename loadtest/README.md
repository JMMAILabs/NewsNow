# Pruebas de carga (k6)

Validan la **escalabilidad real** del sistema: cómo se comporta la latencia (p95) y
el % de error cuando el tráfico sube de golpe (contenido viral / influencers).

> ⚠️ El generador de carga corre en tu máquina, pero **apunta al API ya desplegado**
> en AWS. El autoscaling (Lambda, DynamoDB on-demand, CloudFront) es de AWS. Los *unit tests* (`tests/`) verifican las propiedades que
> **habilitan** escalar (idempotencia, batch, statelessness); la **escala real** se
> mide con esta prueba de carga contra el endpoint desplegado.

## Requisitos

- [k6](https://k6.io) (`scoop install k6`, `choco install k6` o `brew install k6`).
- La infraestructura desplegada (`terraform apply`) → coge la URL del output
  `api_endpoint`.

## Ejecutar contra el API desplegado

```bash
k6 run -e BASE_URL=https://<api-id>.execute-api.eu-west-1.amazonaws.com loadtest/script.js
```

## Smoke de la herramienta (sin AWS)

Para comprobar que el script funciona, se lanza contra un mock local incluido en el
repo ([`mock_server.py`](mock_server.py), multihilo):

```bash
python loadtest/mock_server.py            # escucha en 127.0.0.1:8099
# en otra terminal:
k6 run --vus 10 --duration 10s loadtest/script.js
```

Esto **no** valida el autoscaling (no hay AWS detrás), solo que el arnés de carga
está bien montado.

## Qué mirar en el resultado

- `http_req_duration p(95)` → latencia del percentil 95 (umbral: < 500 ms).
- `http_req_failed` → % de peticiones con error (umbral: < 1%).
- `http_reqs` / `iterations` → throughput (RPS) alcanzado.

Si el p95 se dispara o crecen los errores al subir los VUs, ahí está el cuello de
botella (típicamente: *cold starts* de Lambda → *provisioned concurrency*; o límites
de Bedrock → más batching/cola).
