"""Tests for McpDebugEventLoggingMiddleware (ASGI-safe SSE logging)."""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


class DebugEventLoggingMiddlewareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))

    def _client(self):
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.responses import StreamingResponse
        from starlette.testclient import TestClient

        from debug_event_logging import McpDebugEventLoggingMiddleware

        async def sse(request):
            async def iterator():
                yield b"id: 1\n"
                yield b"data: hi\n\n"

            return StreamingResponse(iterator(), media_type="text/event-stream")

        app = Starlette(middleware=[Middleware(McpDebugEventLoggingMiddleware)])
        app.add_route("/sse", sse, methods=["GET"])
        return TestClient(app)

    def test_disabled_produces_no_debug_output(self) -> None:
        from debug_event_logging import set_enabled

        set_enabled(False)
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self._client() as client:
                res = client.get("/sse", headers={"accept": "text/event-stream"})

        self.assertEqual(res.status_code, 200)
        out = buf.getvalue()
        self.assertNotIn("[Glyphs MCP][Debug]", out)
        self.assertNotIn("[Glyphs MCP][Debug][SSE]", out)

    def test_enabled_logs_sse_frames(self) -> None:
        from debug_event_logging import set_enabled

        set_enabled(True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self._client() as client:
                res = client.get("/sse", headers={"accept": "text/event-stream"})

        self.assertEqual(res.status_code, 200)
        self.assertIn("text/event-stream", res.headers.get("content-type", ""))
        self.assertIn("data: hi", res.text)

        out = buf.getvalue()
        self.assertIn("content-type=text/event-stream", out)
        self.assertIn("[Glyphs MCP][Debug][SSE] data: hi", out)


if __name__ == "__main__":
    unittest.main()

