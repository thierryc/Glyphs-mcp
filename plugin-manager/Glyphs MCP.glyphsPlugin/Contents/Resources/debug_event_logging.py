# encoding: utf-8

"""Optional bounded logging for debugging MCP HTTP and SSE traffic.

This module is deliberately free of Glyphs/AppKit imports so it can be imported
in unit tests outside of Glyphs. The Glyphs UI layer (glyphs_plugin.py) owns the
persisted toggle and calls set_enabled(). Debug records use a stable stream
captured before tool execution redirects process-global stdout and stderr.
"""

from __future__ import division, print_function, unicode_literals

import json
import sys
import threading
import time
from typing import Any, Callable, Dict, Iterable, Optional, Tuple


_ENABLED = False
_DEFAULT_LOG_STREAM = sys.stderr

DEFAULT_MAX_SSE_EXCERPT_CHARS = 512
DEFAULT_MAX_SSE_DETAIL_FRAMES = 8
DEFAULT_MAX_SSE_LINE_BYTES = 2048


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


def _trim_text(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len == 1:
        return "…"
    return text[: max_len - 1] + "…"


def _one_line(text: Any) -> str:
    try:
        return " ".join(str(text or "").split())
    except Exception:
        return ""


def _short_session_id(session_id: str) -> str:
    value = str(session_id or "")
    if len(value) <= 12:
        return value
    return value[:8] + "…" + value[-3:]


class _SseFrameParser:
    """Incrementally summarize SSE frames without retaining unbounded data."""

    def __init__(
        self,
        on_frame: Callable[[Dict[str, Any]], None],
        *,
        max_excerpt_chars: int,
        max_line_bytes: int,
    ) -> None:
        self._on_frame = on_frame
        self._max_excerpt_chars = max(1, int(max_excerpt_chars))
        self._max_line_bytes = max(64, int(max_line_bytes))
        self._pending = bytearray()
        self._pending_discarded_bytes = 0
        self._finished = False
        self._reset_frame()

    def _reset_frame(self) -> None:
        self._event = ""
        self._event_id = ""
        self._data_preview = ""
        self._data_complete = True
        self._frame_bytes = 0
        self._has_field = False
        self._has_non_comment = False
        self._comment_ping = False

    def _append_pending(self, value: bytes) -> None:
        if not value:
            return
        remaining = self._max_line_bytes - len(self._pending)
        if remaining > 0:
            self._pending.extend(value[:remaining])
        self._pending_discarded_bytes += max(0, len(value) - max(0, remaining))

    def _append_data_preview(self, value: str, *, complete: bool) -> None:
        normalized = _one_line(value)
        separator = " " if normalized and self._data_preview else ""
        available = self._max_excerpt_chars - len(self._data_preview)
        addition = separator + normalized
        if available > 0:
            self._data_preview += addition[:available]
        if len(addition) > max(0, available) or not complete:
            self._data_complete = False

    def _consume_line(self, raw: bytes, total_line_bytes: int) -> None:
        if total_line_bytes == 0:
            self._finish_frame()
            return

        line_bytes = raw.rstrip(b"\r")
        if not line_bytes and total_line_bytes == len(raw):
            self._finish_frame()
            return

        self._frame_bytes += int(total_line_bytes)
        retained_complete = total_line_bytes <= len(raw)
        try:
            line = line_bytes.decode("utf-8", errors="replace")
        except Exception:
            line = ""

        if line.startswith(":"):
            self._has_field = True
            comment = _one_line(line[1:]).lower()
            if "ping" in comment or "keepalive" in comment or "keep-alive" in comment:
                self._comment_ping = True
            return

        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        field = field.lower()
        if field == "event":
            self._has_field = True
            self._has_non_comment = True
            self._event = _trim_text(_one_line(value), 80)
        elif field == "id":
            self._has_field = True
            self._has_non_comment = True
            self._event_id = _trim_text(_one_line(value), 80)
        elif field == "data":
            self._has_field = True
            self._has_non_comment = True
            self._append_data_preview(value, complete=retained_complete)
        elif field == "retry":
            self._has_field = True
            self._has_non_comment = True

    def _is_ping(self) -> bool:
        event = self._event.strip().lower()
        if event in {"ping", "keepalive", "keep-alive", "heartbeat"}:
            return True
        if not self._has_non_comment:
            return True
        payload = self._data_preview.strip()
        if payload.lower() in {"ping", "keepalive", "keep-alive", "heartbeat"}:
            return True
        if self._data_complete and payload.startswith("{"):
            try:
                decoded = json.loads(payload)
            except Exception:
                decoded = None
            if isinstance(decoded, dict):
                event_type = str(decoded.get("type") or "").strip().lower()
                if event_type in {"ping", "keepalive", "keep-alive", "heartbeat"}:
                    return True
        return bool(self._comment_ping and not self._data_preview and not self._event)

    def _finish_frame(self) -> None:
        if not self._has_field:
            self._reset_frame()
            return
        frame = {
            "event": self._event or "message",
            "id": self._event_id,
            "data": self._data_preview,
            "dataComplete": bool(self._data_complete),
            "bytes": int(self._frame_bytes),
            "ping": self._is_ping(),
        }
        self._reset_frame()
        self._on_frame(frame)

    def feed(self, body: bytes, *, final: bool = False) -> None:
        if self._finished:
            return
        try:
            value = bytes(body or b"")
        except Exception:
            value = b""

        cursor = 0
        while cursor < len(value):
            newline = value.find(b"\n", cursor)
            if newline < 0:
                self._append_pending(value[cursor:])
                cursor = len(value)
                break
            self._append_pending(value[cursor:newline])
            retained = bytes(self._pending)
            total_line_bytes = len(retained) + self._pending_discarded_bytes
            self._pending.clear()
            self._pending_discarded_bytes = 0
            self._consume_line(retained, total_line_bytes)
            cursor = newline + 1

        if final:
            self.finish()

    def finish(self) -> None:
        if self._finished:
            return
        if self._pending or self._pending_discarded_bytes:
            retained = bytes(self._pending)
            total_line_bytes = len(retained) + self._pending_discarded_bytes
            self._pending.clear()
            self._pending_discarded_bytes = 0
            self._consume_line(retained, total_line_bytes)
        self._finish_frame()
        self._finished = True


class McpDebugEventLoggingMiddleware:
    """ASGI middleware that emits bounded HTTP and SSE diagnostics."""

    def __init__(
        self,
        app: Any,
        *,
        max_sse_excerpt_chars: int = DEFAULT_MAX_SSE_EXCERPT_CHARS,
        max_sse_detail_frames: int = DEFAULT_MAX_SSE_DETAIL_FRAMES,
        max_sse_line_bytes: int = DEFAULT_MAX_SSE_LINE_BYTES,
        sink: Any = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.max_sse_excerpt_chars = max(1, int(max_sse_excerpt_chars))
        self.max_sse_detail_frames = max(0, int(max_sse_detail_frames))
        self.max_sse_line_bytes = max(64, int(max_sse_line_bytes))
        self._sink = _DEFAULT_LOG_STREAM if sink is None else sink
        self._clock = clock
        self._write_lock = threading.Lock()

    def _emit(self, line: str) -> None:
        if not is_enabled():
            return
        try:
            with self._write_lock:
                self._sink.write(str(line) + "\n")
                flush = getattr(self._sink, "flush", None)
                if callable(flush):
                    flush()
        except Exception:
            pass

    async def __call__(self, scope: Dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or not is_enabled():
            await self.app(scope, receive, send)
            return

        started_at = self._clock()
        method = scope.get("method") or "?"
        path = scope.get("path") or "?"
        headers = _decode_headers(scope.get("headers") or ())
        accept = _trim_text(_one_line(headers.get("accept", "")) or "-", 160)
        session_id = _short_session_id(headers.get("mcp-session-id", ""))
        session = " mcp-session-id={}".format(session_id) if session_id else ""
        self._emit(
            "[Glyphs MCP][Debug] -> {method} {path} accept={accept}{session}".format(
                method=method,
                path=path,
                accept=accept,
                session=session,
            )
        )

        is_sse = False
        response_content_type: Optional[str] = None
        response_status: Optional[int] = None
        response_bytes = 0
        total_frames = 0
        logged_frames = 0
        omitted_frames = 0
        ping_frames = 0
        suppression_reported = False
        parser: Optional[_SseFrameParser] = None

        def on_frame(frame: Dict[str, Any]) -> None:
            nonlocal total_frames, logged_frames, omitted_frames
            nonlocal ping_frames, suppression_reported
            total_frames += 1
            if frame.get("ping"):
                ping_frames += 1
                return
            if logged_frames >= self.max_sse_detail_frames:
                omitted_frames += 1
                if not suppression_reported:
                    suppression_reported = True
                    self._emit(
                        "[Glyphs MCP][Debug][SSE] detail limit reached; "
                        "remaining non-ping frames will be summarized"
                    )
                return

            logged_frames += 1
            event = _trim_text(_one_line(frame.get("event")) or "message", 80)
            event_id = _trim_text(_one_line(frame.get("id")), 80)
            data = _trim_text(
                _one_line(frame.get("data")), self.max_sse_excerpt_chars
            )
            truncated = not bool(frame.get("dataComplete"))
            fields = [
                "event={}".format(event),
                "bytes={}".format(int(frame.get("bytes") or 0)),
            ]
            if event_id:
                fields.append("id={}".format(event_id))
            if data:
                fields.append("data={!r}".format(data + ("…" if truncated else "")))
            self._emit("[Glyphs MCP][Debug][SSE] " + " ".join(fields))

        async def send_wrapper(message: Dict[str, Any]) -> None:
            nonlocal is_sse, response_content_type, response_status
            nonlocal response_bytes, parser

            msg_type = message.get("type")
            if msg_type == "http.response.start":
                response_status = message.get("status")
                resp_headers = _decode_headers(message.get("headers") or ())
                response_content_type = resp_headers.get("content-type", "")
                is_sse = "text/event-stream" in (response_content_type or "").lower()
                if is_sse:
                    parser = _SseFrameParser(
                        on_frame,
                        max_excerpt_chars=self.max_sse_excerpt_chars,
                        max_line_bytes=self.max_sse_line_bytes,
                    )
                self._emit(
                    "[Glyphs MCP][Debug] <- {status} {method} {path} content-type={ct}".format(
                        status=int(response_status) if response_status is not None else 0,
                        method=method,
                        path=path,
                        ct=_trim_text(_one_line(response_content_type) or "-", 160),
                    )
                )
            elif msg_type == "http.response.body":
                body = message.get("body") or b""
                try:
                    response_bytes += len(body)
                except Exception:
                    body = b""
                if is_sse and parser is not None:
                    parser.feed(body, final=not bool(message.get("more_body", False)))

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if parser is not None:
                parser.finish()
            try:
                duration_ms = max(0, int(round((self._clock() - started_at) * 1000)))
            except Exception:
                duration_ms = 0
            if is_sse:
                details = (
                    "sseFrames={frames} logged={logged} omitted={omitted} "
                    "pingsSuppressed={pings}"
                ).format(
                    frames=total_frames,
                    logged=logged_frames,
                    omitted=omitted_frames,
                    pings=ping_frames,
                )
            else:
                details = "sseFrames=0"
            self._emit(
                "[Glyphs MCP][Debug] complete {method} {path} status={status} "
                "durationMs={duration} bytes={size} {details}".format(
                    method=method,
                    path=path,
                    status=int(response_status) if response_status is not None else 0,
                    duration=duration_ms,
                    size=response_bytes,
                    details=details,
                )
            )
