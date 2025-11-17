# encoding: utf-8

"""HTTP security helpers for the MCP server inside Glyphs."""

from __future__ import division, print_function, unicode_literals

import os
from typing import Iterable, Optional, Set
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response


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
