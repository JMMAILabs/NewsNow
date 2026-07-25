"""Servidor mock para el *smoke* de k6 sin AWS.

Responde JSON en /articles y /daily-summary. Es multihilo (ThreadingHTTPServer)
para no ser el cuello de botella durante el smoke. Solo sirve para comprobar que
el arnés de k6 está bien montado; NO valida el autoscaling (eso se mide contra el
API desplegado en AWS).

Uso:
    python loadtest/mock_server.py            # escucha en 127.0.0.1:8099
    # en otra terminal:
    k6 run --vus 10 --duration 10s loadtest/script.js
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_ARTICLES = {
    "articles": [
        {"id": "a1", "category": "tecnologia", "title": "Noticia de ejemplo 1",
         "summary": "Resumen de ejemplo.", "tags": ["demo"]},
        {"id": "a2", "category": "economia", "title": "Noticia de ejemplo 2",
         "summary": "Resumen de ejemplo.", "tags": ["demo"]},
    ],
    "count": 2,
}
_DAILY = {"intro": "Boletin de ejemplo.", "highlights": ["h1", "h2"], "digest": "..."}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (nombre impuesto por BaseHTTPRequestHandler)
        body = _DAILY if self.path.startswith("/daily-summary") else _ARTICLES
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_a):  # silencia un log por cada request
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8099), Handler)
    print("mock en http://127.0.0.1:8099  (Ctrl+C para parar)")
    server.serve_forever()
