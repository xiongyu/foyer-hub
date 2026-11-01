"""Small dependency-free dashboard and JSON API."""

from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from .service import IndoorTerminalService, OperationRejected


STATIC_DIR = Path(__file__).with_name("static")


class DashboardServer:
    def __init__(self, service: IndoorTerminalService, host: str, port: int, api_token: str = "") -> None:
        self.service = service
        self.api_token = api_token
        handler = self._handler_class()
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True
        self._thread: Optional[threading.Thread] = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.httpd.server_address[:2]
        return str(host), int(port)

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "IndoorDashboard/0.1"

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _authorized(self) -> bool:
                if not outer.api_token:
                    return True
                bearer = self.headers.get("Authorization", "")
                supplied = self.headers.get("X-API-Token", "")
                return bearer == f"Bearer {outer.api_token}" or supplied == outer.api_token

            def _json(self, status: int, payload: Dict[str, Any]) -> None:
                encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(encoded)

            def _read_json(self) -> Dict[str, Any]:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError as exc:
                    raise ValueError("invalid Content-Length") from exc
                if not 0 <= length <= 16384:
                    raise ValueError("request body is too large")
                if not length:
                    return {}
                value = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError("JSON body must be an object")
                return value

            def _serve_static(self, name: str) -> None:
                allowed = {
                    "": ("index.html", "text/html; charset=utf-8"),
                    "/": ("index.html", "text/html; charset=utf-8"),
                    "/index.html": ("index.html", "text/html; charset=utf-8"),
                    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                }
                item = allowed.get(name)
                if item is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                body = (STATIC_DIR / item[0]).read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", item[1])
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if not parsed.path.startswith("/api/"):
                    self._serve_static(parsed.path)
                    return
                if not self._authorized():
                    self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
                    return
                if parsed.path in ("/api/status", "/api/health"):
                    self._json(HTTPStatus.OK, {"ok": True, "status": outer.service.status()})
                    return
                if parsed.path == "/api/events":
                    query = parse_qs(parsed.query)
                    try:
                        after = int(query.get("after", ["0"])[0])
                    except ValueError:
                        after = 0
                    events = outer.service.events.since(after)
                    self._json(
                        HTTPStatus.OK,
                        {"ok": True, "events": events, "latest": outer.service.events.latest_sequence},
                    )
                    return
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if not self._authorized():
                    self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
                    return
                try:
                    body = self._read_json()
                    if parsed.path == "/api/register":
                        result = outer.service.register()
                    elif parsed.path == "/api/discover":
                        result = outer.service.discover_center()
                    elif parsed.path == "/api/elevator/call":
                        result = outer.service.call_elevator(str(body.get("confirmation", "")))
                    elif parsed.path == "/api/rest/sync":
                        result = outer.service.sync_rest()
                    else:
                        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
                        return
                except OperationRejected as exc:
                    self._json(HTTPStatus.CONFLICT, {"ok": False, "error": str(exc)})
                    return
                except (ValueError, RuntimeError, OSError) as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                    return
                self._json(HTTPStatus.OK, {"ok": True, "result": result})

        return Handler

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="indoor-web", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
