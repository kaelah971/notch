"""Minimal stdlib HTTP server for the S6 API."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from .app import WebAPI


class ApiHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(app: WebAPI) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "NotchWebAPI/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            # No headers, query strings or bodies in logs.
            sys.stderr.write(
                "%s - %s\n" % (self.address_string(), fmt % args)
            )

        def _origin(self) -> str | None:
            origin = self.headers.get("Origin")
            return origin if origin in app.config.cors_origins else None

        def _cors(self) -> None:
            origin = self._origin()
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header(
                    "Access-Control-Allow-Headers", "Content-Type, Accept, Authorization"
                )
                self.send_header("Access-Control-Max-Age", "600")

        def _write(self, status: int, payload: dict[str, Any]) -> None:
            raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self._cors()
            self.end_headers()
            self.wfile.write(raw)

        def _body(self) -> Any:
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                return None
            if length > app.config.max_body_bytes:
                return "TOO_LARGE"
            if length <= 0:
                return None
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                return "INVALID_JSON"

        def _handle(self, method: str) -> None:
            parsed = urlparse(self.path)
            query = {
                key: values[-1]
                for key, values in parse_qs(parsed.query, keep_blank_values=True).items()
            }
            body = self._body() if method == "POST" else None
            if body == "TOO_LARGE":
                self._write(
                    413,
                    {
                        "error": {
                            "code": "BODY_TOO_LARGE",
                            "message": "request body exceeds the configured limit",
                        }
                    },
                )
                return
            if body == "INVALID_JSON":
                self._write(
                    400,
                    {
                        "error": {
                            "code": "INVALID_JSON",
                            "message": "request body is not valid JSON",
                        }
                    },
                )
                return
            status, payload = app.handle(
                method,
                parsed.path,
                query,
                body,
                client=self.client_address[0],
                headers={key: value for key, value in self.headers.items()},
            )
            self._write(status, payload)

        def do_GET(self) -> None:  # noqa: N802
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

    return Handler


def create_server(app: WebAPI, *, host: str, port: int) -> ApiHTTPServer:
    return ApiHTTPServer((host, port), make_handler(app))


def serve(app: WebAPI, *, host: str, port: int) -> None:
    server = create_server(app, host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        app.close()


def serve_in_thread(app: WebAPI, *, host: str = "127.0.0.1", port: int = 0):
    server = create_server(app, host=host, port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
