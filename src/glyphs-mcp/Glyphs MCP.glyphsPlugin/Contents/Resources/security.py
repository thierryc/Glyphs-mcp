# encoding: utf-8

"""HTTP security helpers for the MCP server inside Glyphs."""

from __future__ import division, print_function, unicode_literals

import os
import uuid
from typing import Iterable, Optional, Set
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response


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


class McpSessionIdMiddleware(BaseHTTPMiddleware):
    """Ensure an Mcp-Session-Id header exists for initial requests.

    Some MCP clients expect the server to accept the initial Streamable HTTP
    connection without a session id and return one to reuse. FastMCP's HTTP
    transport can otherwise reject the first request with "Missing session ID".
    """

    header_name = b"mcp-session-id"

    async def dispatch(self, request: Request, call_next):
        accept = (request.headers.get("accept") or "").lower()
        if request.method != "GET" or "text/event-stream" not in accept:
            return await call_next(request)

        scope = request.scope
        headers = list(scope.get("headers") or [])

        has_session_id = any(key.lower() == self.header_name for key, _ in headers)
        injected_session_id: Optional[str] = None

        if not has_session_id:
            injected_session_id = str(uuid.uuid4())
            headers.append((self.header_name, injected_session_id.encode("utf-8")))
            scope["headers"] = headers

        response: Response = await call_next(request)

        if injected_session_id and "mcp-session-id" not in response.headers:
            response.headers["mcp-session-id"] = injected_session_id

        return response


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
