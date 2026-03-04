# encoding: utf-8

"""Optional verbose logging for debugging MCP HTTP + SSE traffic.

This module is deliberately free of Glyphs/AppKit imports so it can be imported
in unit tests outside of Glyphs. The Glyphs UI layer (glyphs_plugin.py) is
responsible for persisting the toggle and calling set_enabled().
"""

from __future__ import division, print_function, unicode_literals

from typing import Any, Dict, Iterable, List, Optional, Tuple


_ENABLED = False


def set_enabled(enabled: bool) -> None:
    global _ENABLED
    try:
        _ENABLED = bool(enabled)
    except Exception:
        _ENABLED = False


def is_enabled() -> bool:
    try:
        return bool(_ENABLED)
    except Exception:
        return False


def _decode_headers(headers: Iterable[Tuple[bytes, bytes]]) -> Dict[str, str]:
    decoded: Dict[str, str] = {}
    for key, value in headers or ():
        try:
            k = key.decode("utf-8", errors="replace").lower()
        except Exception:
            continue
        try:
            v = value.decode("utf-8", errors="replace")
        except Exception:
            v = ""
        decoded[k] = v
    return decoded


def _trim_line(line: str, max_len: int) -> str:
    if max_len <= 0:
        return line
    if len(line) <= max_len:
        return line
    return line[: max_len - 1] + "…"


class McpDebugEventLoggingMiddleware:
    """ASGI middleware that logs HTTP requests and SSE output when enabled."""

    def __init__(self, app: Any, *, max_sse_line_len: int = 2048) -> None:
        self.app = app
        self.max_sse_line_len = int(max_sse_line_len) if max_sse_line_len is not None else 2048

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or not is_enabled():
            await self.app(scope, receive, send)
            return

        method = scope.get("method") or "?"
        path = scope.get("path") or "?"
        headers = _decode_headers(scope.get("headers") or ())
        accept = headers.get("accept", "")
        session_id = headers.get("mcp-session-id", "")

        try:
            print(
                "[Glyphs MCP][Debug] -> {method} {path} accept={accept}{session}".format(
                    method=method,
                    path=path,
                    accept=accept if accept else "-",
                    session=(" mcp-session-id={}".format(session_id) if session_id else ""),
                )
            )
        except Exception:
            pass

        is_sse = False
        response_content_type: Optional[str] = None
        response_status: Optional[int] = None

        async def send_wrapper(message: Dict[str, Any]) -> None:
            nonlocal is_sse, response_content_type, response_status

            msg_type = message.get("type")
            if msg_type == "http.response.start":
                response_status = message.get("status")
                resp_headers = _decode_headers(message.get("headers") or ())
                response_content_type = resp_headers.get("content-type", "")
                is_sse = "text/event-stream" in (response_content_type or "").lower()
                try:
                    print(
                        "[Glyphs MCP][Debug] <- {status} {method} {path} content-type={ct}".format(
                            status=int(response_status) if response_status is not None else 0,
                            method=method,
                            path=path,
                            ct=response_content_type if response_content_type else "-",
                        )
                    )
                except Exception:
                    pass

            elif msg_type == "http.response.body" and is_sse:
                body = message.get("body") or b""
                if body:
                    try:
                        text = body.decode("utf-8", errors="replace")
                    except Exception:
                        text = ""

                    if text:
                        # SSE frames are line-based. Log the useful lines only.
                        for raw_line in text.splitlines():
                            line = raw_line.rstrip("\r")
                            if not line:
                                continue
                            if not (
                                line.startswith("data:")
                                or line.startswith("id:")
                                or line.startswith("event:")
                                or line.startswith("retry:")
                                or line.startswith(":")
                            ):
                                continue
                            try:
                                trimmed = _trim_line(line, self.max_sse_line_len)
                                print("[Glyphs MCP][Debug][SSE] {line}".format(line=trimmed))
                            except Exception:
                                pass

            await send(message)

        await self.app(scope, receive, send_wrapper)

