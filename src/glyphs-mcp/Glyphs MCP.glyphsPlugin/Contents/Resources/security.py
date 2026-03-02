# encoding: utf-8

"""HTTP security helpers for the MCP server inside Glyphs."""

from __future__ import division, print_function, unicode_literals

import json
import os
from typing import Iterable, Optional, Set, Dict, Any, Tuple
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.types import Scope, Receive, Send

try:
    from versioning import get_plugin_version
except Exception:  # pragma: no cover - tests may import without bundle layout
    get_plugin_version = None


class McpNormalizeMcpPathMiddleware:
    """Normalize `/mcp` to `/mcp/` without relying on HTTP redirects.

    Some clients POST to `/mcp` (no trailing slash) and do not reliably follow
    Starlette's 307 redirect. Rewrite the scope path early so routing matches
    the mounted Streamable HTTP app.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            scope = dict(scope)
            scope["path"] = "/mcp/"
            scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


class McpNoOAuthWellKnownMiddleware(BaseHTTPMiddleware):
    """Return 404 for OAuth discovery endpoints when OAuth is not supported.

    Some MCP clients/proxies probe OAuth well-known endpoints even for local
    servers that don't require authentication. When those probes are routed into
    the Streamable HTTP transport, FastMCP can reply with 406/400 errors that
    look like server failures. Intercept the probes early and respond with 404
    so clients can fall back cleanly.
    """

    def __init__(self, app):
        super().__init__(app)
        self._paths = {
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-authorization-server/mcp",
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self._paths:
            return PlainTextResponse("Not Found", status_code=404)

        # Some clients mistakenly try discovery under the MCP base path.
        if path.startswith("/mcp/.well-known/"):
            return PlainTextResponse("Not Found", status_code=404)

        return await call_next(request)


class McpDiscoveryMiddleware(BaseHTTPMiddleware):
    """Return a JSON discovery payload for non-SSE browser requests.

    The MCP Streamable HTTP transport expects clients to connect using SSE.
    Opening the endpoint in a browser typically results in a 400 error from the
    underlying transport. This middleware makes `GET /mcp/` return a small JSON
    payload instead, without impacting proper SSE connections.
    """

    def __init__(self, app, paths=("/mcp", "/mcp/")):
        super().__init__(app)
        self.paths = set(paths)

    async def dispatch(self, request: Request, call_next):
        if request.method != "GET":
            return await call_next(request)

        if request.url.path not in self.paths:
            return await call_next(request)

        accept = (request.headers.get("accept") or "").lower()
        if "text/event-stream" in accept:
            return await call_next(request)

        return JSONResponse(
            {
                "ok": True,
                "transport": "streamable-http",
                "message": "This is an MCP endpoint. Use an MCP client to connect via SSE.",
                "sse": {"accept": "text/event-stream", "sessionHeader": "Mcp-Session-Id"},
            }
        )


def _allowed_hosts_from_env(env_value: str) -> Set[str]:
    entries = set()
    for raw in env_value.split(","):
        host = raw.strip()
        if host:
            entries.add(host.lower())
    return entries


class OriginValidationMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Origin header is not explicitly whitelisted."""

    def __init__(self, app, allowed_hosts: Optional[Iterable[str]] = None):
        super().__init__(app)
        default_hosts = {"127.0.0.1", "localhost"}
        hosts = set(h.lower() for h in (allowed_hosts or default_hosts))

        extra = os.environ.get("GLYPHS_MCP_ALLOWED_ORIGINS", "")
        hosts.update(_allowed_hosts_from_env(extra))

        self.allowed_hosts = hosts or default_hosts

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        if not origin:
            return await call_next(request)

        parsed = urlparse(origin)
        hostname = (parsed.hostname or "").lower()

        if hostname in self.allowed_hosts:
            return await call_next(request)

        return PlainTextResponse("Forbidden: Invalid origin", status_code=403)


class StaticTokenAuthMiddleware(BaseHTTPMiddleware):
    """Simple bearer-style token authentication controlled via env vars."""

    def __init__(self, app, token: Optional[str] = None):
        super().__init__(app)
        env_token = os.environ.get("GLYPHS_MCP_AUTH_TOKEN")
        self.expected_token = token or env_token

    async def dispatch(self, request: Request, call_next):
        if not self.expected_token:
            return await call_next(request)

        header = request.headers.get("authorization") or ""
        provided = None
        if header.lower().startswith("bearer "):
            provided = header.split(" ", 1)[1]
        else:
            provided = request.headers.get("mcp-auth-token")

        if provided and provided == self.expected_token:
            return await call_next(request)

        return PlainTextResponse("Unauthorized", status_code=401)


def _should_preserve_response(response: Response) -> bool:
    """Return True if the response should not be modified (e.g. SSE)."""
    try:
        content_type = (response.headers.get("content-type") or "").lower()
    except Exception:
        content_type = ""

    if "text/event-stream" in content_type:
        return True

    return False


async def _extract_body_text(response: Response, limit: int = 4096) -> str:
    """Best-effort body extraction for debugging/wrapping errors.

    Note: when used inside BaseHTTPMiddleware, responses returned by call_next()
    are often wrapped as streaming responses. In that case, `response.body` may
    be empty and the real bytes are available via `response.body_iterator`.
    """
    try:
        body = getattr(response, "body", b"") or b""
        if isinstance(body, str):
            return body[:limit]
        if isinstance(body, (bytes, bytearray)) and body:
            return bytes(body[:limit]).decode("utf-8", errors="replace")
    except Exception:
        pass

    iterator = getattr(response, "body_iterator", None)
    if iterator is None:
        return ""

    collected = b""
    try:
        async for chunk in iterator:
            if chunk is None:
                continue
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8", errors="replace")
            if not isinstance(chunk, (bytes, bytearray)):
                try:
                    chunk = str(chunk).encode("utf-8", errors="replace")
                except Exception:
                    continue

            if len(collected) < limit:
                remaining = limit - len(collected)
                collected += bytes(chunk[:remaining])

            if len(collected) >= limit:
                # Avoid fully draining large/slow streaming bodies. Best-effort
                # close the iterator early to release resources.
                closer = getattr(iterator, "aclose", None) or getattr(iterator, "close", None)
                if closer is not None:
                    try:
                        result = closer()
                        if hasattr(result, "__await__"):
                            await result
                    except Exception:
                        pass
                break
    except Exception:
        return collected.decode("utf-8", errors="replace")

    return collected.decode("utf-8", errors="replace")


def _copy_passthrough_headers(src: Response, dst: Response) -> None:
    """Copy headers that clients rely on (session + CORS + auth hints)."""
    passthrough_names = {
        "mcp-session-id",
        "access-control-allow-origin",
        "access-control-allow-methods",
        "access-control-allow-headers",
        "access-control-expose-headers",
        "access-control-max-age",
        "vary",
        "www-authenticate",
    }

    for name, value in (src.headers or {}).items():
        if name.lower() in passthrough_names:
            try:
                dst.headers[name] = value
            except Exception:
                continue


def _classify_error(request: Request, response: Response, detail: str) -> Tuple[str, str]:
    """Return (message, how_to_fix) tuned for common handshake failures."""
    normalized = (detail or "").lower()
    status_code = getattr(response, "status_code", None)

    if (
        request.method.upper() == "POST"
        and request.url.path.startswith("/mcp")
        and request.headers.get("mcp-session-id")
        and (normalized.strip() == "not found" or (status_code == 404 and "not found" in normalized))
    ):
        return (
            "Session expired (server restarted).",
            "Drop the Mcp-Session-Id and start a new MCP session: send initialize (POST /mcp/) "
            "then notifications/initialized, then retry the tool call. "
            "If the client cannot reinitialize automatically, restart the MCP client session.",
        )

    if "no valid session id provided" in normalized or "invalid or expired session id" in normalized:
        return (
            "Session expired (server restarted).",
            "Drop the Mcp-Session-Id and start a new MCP session: send initialize (POST /mcp/) "
            "then notifications/initialized, then retry tools/list or tools/call. "
            "If the client does not automatically reinitialize, restart the MCP client session.",
        )

    if "missing session" in normalized:
        return (
            "Missing Mcp-Session-Id header.",
            "For stateful Streamable HTTP sessions, reuse the Mcp-Session-Id returned by the server. "
            "If you are starting a new session, call initialize first (no session id), then send notifications/initialized.",
        )

    if "not acceptable" in normalized and "must accept both" in normalized:
        return (
            "Invalid Accept header for MCP POST request.",
            "For POST /mcp/, include Accept: application/json, text/event-stream. "
            "For GET /mcp/ (SSE stream), include Accept: text/event-stream.",
        )

    if "accept" in normalized and "event-stream" in normalized:
        return (
            "Invalid Accept header for MCP endpoint.",
            "For POST /mcp/, include Accept: application/json, text/event-stream. "
            "For GET /mcp/ (SSE stream), include Accept: text/event-stream.",
        )

    if "initialized" in normalized or "initialize" in normalized:
        return (
            "MCP session is not initialized.",
            "Call initialize first, then send notifications/initialized before calling tools/list or tools/call.",
        )

    # Default: reflect downstream detail but keep guidance about handshake.
    return (
        "MCP request failed.",
        "If this happened during reconnect, drop the Mcp-Session-Id and start a new MCP session: "
        "send initialize + notifications/initialized, then retry the tool call.",
    )


def _wants_sse(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "text/event-stream" in accept


async def _request_jsonrpc_id(request: Request) -> Any:
    """Best-effort extraction of JSON-RPC request id for POST requests."""
    if request.method.upper() != "POST":
        return None
    try:
        body_bytes = await request.body()
        if not body_bytes:
            return None
        parsed = json.loads(body_bytes.decode("utf-8", errors="replace"))
        if isinstance(parsed, dict):
            return parsed.get("id")
        # Batch requests are not correlated to a single id here.
        return None
    except Exception:
        return None


def _error_payload(
    request: Request,
    status_code: int,
    message: str,
    detail: str,
    how_to_fix: str,
    *,
    request_id: Any = None,
) -> Dict[str, Any]:
    accept = request.headers.get("accept") or ""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": -32000,
            "message": message,
            "data": {
                "httpStatus": int(status_code),
                "detail": detail,
                "expectedAccept": "application/json, text/event-stream",
                "gotAccept": accept,
                "expectedHeaders": [
                    "Accept: application/json, text/event-stream (POST)",
                    "Content-Type: application/json (POST)",
                    "Mcp-Session-Id (after initialize)",
                ],
                "howToFix": how_to_fix,
                "request": {"method": request.method, "path": request.url.path},
            },
        },
    }


def _error_response(
    request: Request,
    status_code: int,
    payload: Dict[str, Any],
) -> Response:
    """Return an error response in a client-compatible format.

    For MCP Streamable HTTP, it's acceptable (and often preferable) to return
    application/json for all errors, even when the request Accept includes SSE.
    This makes clients more likely to decode the error payload successfully.
    """
    return JSONResponse(payload, status_code=int(status_code))


class McpErrorEnvelopeMiddleware(BaseHTTPMiddleware):
    """Normalize all non-2xx responses into JSON with explicit hints.

    This is primarily a debuggability and protocol-safety layer for MCP clients
    that fail hard on responses that contain a body but no Content-Type header.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Lightweight diagnostics endpoint that never depends on SSE/session setup.
        if request.method == "GET" and path == "/healthz":
            version = "dev"
            if get_plugin_version is not None:
                try:
                    version = str(get_plugin_version())
                except Exception:
                    version = "dev"

            glyphs_reachable = False
            try:
                from GlyphsApp import Glyphs  # type: ignore[import-not-found]

                glyphs_reachable = bool(Glyphs)
            except Exception:
                glyphs_reachable = False

            return JSONResponse(
                {"ok": True, "version": version, "glyphsReachable": glyphs_reachable},
                status_code=200,
            )

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            req_id = await _request_jsonrpc_id(request)
            payload = _error_payload(
                request,
                500,
                "Internal server error.",
                str(exc),
                "Retry the request. If this persists, restart Glyphs and start the MCP server again.",
                request_id=req_id,
            )
            return _error_response(request, 500, payload)

        if _should_preserve_response(response):
            return response

        # Safety net: never return a non-empty body without a Content-Type header.
        try:
            content_type = response.headers.get("content-type")
        except Exception:
            content_type = None

        try:
            body = getattr(response, "body", b"") or b""
        except Exception:
            body = b""

        if (not content_type) and body:
            try:
                response.headers["Content-Type"] = "text/plain; charset=utf-8"
            except Exception:
                pass

        # Normalize errors to JSON for debuggability.
        status_code = getattr(response, "status_code", 200) or 200
        if 200 <= int(status_code) < 300:
            return response

        detail = await _extract_body_text(response)
        effective_status_code = int(status_code)

        # Spec-correct stale-session signal:
        # When a client sends an unknown Mcp-Session-Id (common after server restart),
        # the underlying streamable HTTP session manager can respond with 400
        # "No valid session ID provided". MCP transport semantics treat this as a
        # terminated/expired session, which should surface as 404 so clients know
        # to re-initialize without a session id.
        try:
            normalized_detail = (detail or "").lower()
        except Exception:
            normalized_detail = ""

        try:
            has_session_id = bool(request.headers.get("mcp-session-id"))
        except Exception:
            has_session_id = False

        if request.url.path.startswith("/mcp") and has_session_id:
            if (
                "no valid session id provided" in normalized_detail
                or "invalid or expired session id" in normalized_detail
                or normalized_detail.strip() == "not found"
            ) and "missing session id" not in normalized_detail:
                effective_status_code = 404
                # Keep payload detail consistent with the normalized 404 status.
                try:
                    stripped = (detail or "").lstrip()
                    if stripped.lower().startswith("bad request:"):
                        detail = "Not Found:" + stripped[len("Bad Request:") :]
                except Exception:
                    pass

        message, how_to_fix = _classify_error(request, response, detail)
        req_id = await _request_jsonrpc_id(request)
        payload = _error_payload(
            request,
            int(effective_status_code),
            message,
            detail,
            how_to_fix,
            request_id=req_id,
        )

        wrapped = _error_response(request, int(effective_status_code), payload)
        _copy_passthrough_headers(response, wrapped)
        return wrapped
