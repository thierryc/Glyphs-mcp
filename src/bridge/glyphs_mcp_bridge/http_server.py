"""Authenticated loopback JSON server; this is not an MCP server."""

from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

from .core import BridgeCore, BridgeError


MAX_REQUEST_BYTES = 4 * 1024 * 1024


class _LoopbackServer(ThreadingHTTPServer):
    daemon_threads = True


class BridgeHTTPServer:
    def __init__(
        self,
        core: BridgeCore,
        main_thread: Any,
        *,
        token: str,
        host: str = "127.0.0.1",
        port: int = 9681,
    ) -> None:
        if not token:
            raise ValueError("the bridge requires a local authentication token")
        self.core = core
        self.main_thread = main_thread
        self.token = str(token)
        handler = self._handler()
        self.server = _LoopbackServer((host, int(port)), handler)
        self.thread: Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        host, port = self.server.server_address[:2]
        return str(host), int(port)

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.thread = Thread(target=lambda: self.server.serve_forever(poll_interval=0.05), name="glyphs-mcp-bridge", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "GlyphsMCPBridge/0.1"

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def do_POST(self) -> None:  # noqa: N802
                supplied = self.headers.get("Authorization", "")
                expected = "Bearer " + owner.token
                if not hmac.compare_digest(supplied, expected):
                    self._reply(401, {"ok": False, "error": {"code": "unauthorized", "message": "invalid bridge token"}})
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    size = -1
                if size < 0 or size > MAX_REQUEST_BYTES:
                    self._reply(413, {"ok": False, "error": {"code": "request_too_large", "message": "request is too large"}})
                    return
                try:
                    payload = json.loads(self.rfile.read(size) or b"{}")
                    if not isinstance(payload, dict):
                        raise ValueError("JSON root must be an object")
                    result = owner.main_thread.call(lambda: self._route(payload))
                    self._reply(200, {"ok": True, "data": result})
                except BridgeError as exc:
                    self._reply(409, {"ok": False, "error": exc.as_dict()})
                except (ValueError, TypeError) as exc:
                    self._reply(400, {"ok": False, "error": {"code": "invalid_request", "message": str(exc)}})
                except TimeoutError as exc:
                    details = {"execution": getattr(exc, "execution", "uncertain")}
                    patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {}
                    job_id = payload.get("jobId") or patch.get("jobId")
                    if job_id:
                        details["jobId"] = job_id
                    save = payload.get("save") if isinstance(payload.get("save"), dict) else {}
                    save_id = payload.get("saveId") or save.get("saveId")
                    if save_id:
                        details["saveId"] = save_id
                    self._reply(503, {"ok": False, "error": {"code": "glyphs_busy", "message": str(exc), "details": details}})
                except Exception as exc:
                    self._reply(500, {"ok": False, "error": {"code": "bridge_failed", "message": str(exc) or exc.__class__.__name__}})

            def _route(self, payload: dict[str, Any]) -> Any:
                if owner.core.paused:
                    raise BridgeError("server_stopped", "the Glyphs MCP server is stopped")
                if self.path == "/v1/status":
                    return owner.core.status()
                if self.path == "/v1/documents":
                    return owner.core.list_documents()
                if self.path == "/v1/entities":
                    return owner.core.read_entities(
                        str(payload.get("documentId") or ""),
                        payload.get("entities"),
                        payload.get("fields"),
                    )
                if self.path == "/v1/compile-features":
                    return owner.core.compile_features(payload.get("compile"))
                if self.path == "/v1/apply":
                    return owner.core.begin_apply(payload.get("patch"), approved_overwrites=payload.get("approvedOverwrites"))
                if self.path == "/v1/operation":
                    return owner.core.operation(str(payload.get("jobId") or ""))
                if self.path == "/v1/discard":
                    return owner.core.discard(str(payload.get("jobId") or ""))
                if self.path == "/v1/accept":
                    return owner.core.begin_accept(
                        str(payload.get("jobId") or ""), payload.get("save")
                    )
                if self.path == "/v1/accept/complete":
                    return owner.core.complete_accept(
                        str(payload.get("jobId") or ""),
                        verified=payload.get("verified") is True,
                        receipt=payload.get("receipt"),
                        error=payload.get("error"),
                    )
                if self.path == "/v1/save":
                    return owner.core.begin_save(payload.get("save"))
                if self.path == "/v1/save-operation":
                    return owner.core.save_operation(str(payload.get("saveId") or ""))
                raise BridgeError("not_found", "unknown bridge route")

            def _reply(self, status: int, value: dict[str, Any]) -> None:
                body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler
