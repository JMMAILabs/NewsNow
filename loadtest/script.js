// Prueba de carga con k6 — perfil "pico de influencer".
//
// El generador corre en LOCAL, pero apunta al API DESPLEGADO (API Gateway).
// Para el smoke de la herramienta se usa un mock local por defecto.
//
//   k6 run -e BASE_URL=https://<api-id>.execute-api.eu-west-1.amazonaws.com loadtest/script.js
//
// Valida la escalabilidad real: latencia p95 y % de error mientras el tráfico
// sube de golpe (contenido viral). El grueso es LECTURA de portada, que es lo
// que CloudFront/API cachean y lo que aguanta el pico.

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8099";
const errores = new Rate("errores");

export const options = {
  // Rampa rápida → meseta alta → bajada (simula un pico de influencer).
  stages: [
    { duration: "20s", target: 50 },
    { duration: "40s", target: 200 },
    { duration: "20s", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"], // < 1% de errores
    http_req_duration: ["p(95)<500"], // p95 por debajo de 500 ms
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/articles`);
  const ok = check(res, {
    "status 200": (r) => r.status === 200,
    "es JSON": (r) => (r.headers["Content-Type"] || "").includes("json"),
  });
  errores.add(!ok);
  sleep(1);
}
