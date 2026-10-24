#!/usr/bin/env python3

import http.client
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 11435

OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class OllamaProxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def do_GET(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def do_DELETE(self):
        self.forward()

    def do_HEAD(self):
        self.forward()

    def forward(self):
        path = urlsplit(self.path).path

        # Разрешаем только маршруты Ollama.
        if not (
            path.startswith("/api/")
            or path.startswith("/v1/")
            or path == "/api"
            or path == "/v1"
        ):
            self.send_error(404, "Unknown API route")
            return

        length = self.headers.get("Content-Length")

        if self.headers.get("Transfer-Encoding"):
            self.send_error(501, "Chunked request bodies unsupported")
            return

        if self.command in ("POST", "PUT") and length is None:
            self.send_error(411, "Content-Length required")
            return

        body = self.rfile.read(int(length)) if length is not None else None

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_HEADERS
            and key.lower() not in {
                "host",
                "authorization",
                "content-length",
                "accept-encoding",
            }
        }

        headers["Accept-Encoding"] = "identity"

        conn = http.client.HTTPConnection(
            OLLAMA_HOST,
            OLLAMA_PORT,
            timeout=600,
        )

        try:
            conn.request(
                self.command,
                self.path,
                body=body,
                headers=headers,
            )

            response = conn.getresponse()

            self.send_response(response.status, response.reason)

            for key, value in response.getheaders():
                if key.lower() not in HOP_HEADERS:
                    self.send_header(key, value)

            self.send_header("Connection", "close")
            self.end_headers()

            if self.command != "HEAD":
                while True:
                    chunk = response.read(16384)
                    if not chunk:
                        break

                    self.wfile.write(chunk)
                    self.wfile.flush()

            self.close_connection = True

        except (OSError, http.client.HTTPException) as exc:
            logging.error("Proxy error: %s", exc)
            if not self.wfile.closed:
                try:
                    self.send_error(502, "Ollama upstream error")
                except OSError:
                    pass
        finally:
            conn.close()


if __name__ == "__main__":
    server = ThreadingHTTPServer(
        (LISTEN_HOST, LISTEN_PORT),
        OllamaProxy,
    )

    logging.info(
        "Ollama proxy listening on %s:%s -> %s:%s",
        LISTEN_HOST,
        LISTEN_PORT,
        OLLAMA_HOST,
        OLLAMA_PORT,
    )

    server.serve_forever()
