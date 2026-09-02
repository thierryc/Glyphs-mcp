"""Tests for bounded, capture-safe MCP HTTP and SSE logging."""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


_DEFAULT_SINK = object()


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

    def tearDown(self) -> None:
        from debug_event_logging import set_enabled

        set_enabled(False)

    def _client(self, chunks=None, *, sink=_DEFAULT_SINK, **middleware_options):
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.responses import StreamingResponse
        from starlette.testclient import TestClient

        from debug_event_logging import McpDebugEventLoggingMiddleware

        response_chunks = list(chunks or (b"id: 1\r\n", b"data: hi\r\n\r\n"))

        async def sse(_request):
            async def iterator():
                for chunk in response_chunks:
                    yield chunk

            return StreamingResponse(iterator(), media_type="text/event-stream")

        options = dict(middleware_options)
        if sink is not _DEFAULT_SINK:
            options["sink"] = sink
        app = Starlette(
            middleware=[Middleware(McpDebugEventLoggingMiddleware, **options)]
        )
        app.add_route("/sse", sse, methods=["GET"])
        return TestClient(app)

    def test_disabled_produces_no_debug_output(self) -> None:
        from debug_event_logging import set_enabled

        set_enabled(False)
        debug = io.StringIO()
        with self._client(sink=debug) as client:
            response = client.get("/sse", headers={"accept": "text/event-stream"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(debug.getvalue(), "")

    def test_enabled_logs_one_compact_sse_frame_and_completion(self) -> None:
        from debug_event_logging import set_enabled

        set_enabled(True)
        debug = io.StringIO()
        with self._client(sink=debug) as client:
            response = client.get("/sse", headers={"accept": "text/event-stream"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        self.assertIn("data: hi", response.text)
        output = debug.getvalue()
        self.assertIn("content-type=text/event-stream", output)
        self.assertIn("[Glyphs MCP][Debug][SSE] event=message", output)
        self.assertIn("id=1", output)
        self.assertIn("data='hi'", output)
        self.assertIn("sseFrames=1 logged=1 omitted=0 pingsSuppressed=0", output)

    def test_ping_frames_are_suppressed_and_aggregated(self) -> None:
        from debug_event_logging import set_enabled

        set_enabled(True)
        chunks = [
            b": ping - 2026-09-02T12:00:00Z\n\n",
            b"event: ping\ndata: {\"type\":\"ping\"}\n\n",
            b"event: message\ndata: useful result\n\n",
        ]
        debug = io.StringIO()
        with self._client(chunks, sink=debug) as client:
            response = client.get("/sse")

        self.assertEqual(response.status_code, 200)
        output = debug.getvalue()
        self.assertNotIn("2026-09-02T12:00:00Z", output)
        self.assertNotIn("event=ping", output)
        self.assertIn("data='useful result'", output)
        self.assertIn("sseFrames=3 logged=1 omitted=0 pingsSuppressed=2", output)

    def test_detail_count_and_excerpt_length_are_bounded(self) -> None:
        from debug_event_logging import set_enabled

        set_enabled(True)
        chunks = [
            "event: message\ndata: {}-{}\n\n".format(index, "x" * 100).encode()
            for index in range(5)
        ]
        debug = io.StringIO()
        with self._client(
            chunks,
            sink=debug,
            max_sse_detail_frames=2,
            max_sse_excerpt_chars=20,
        ) as client:
            response = client.get("/sse")

        self.assertEqual(response.status_code, 200)
        output = debug.getvalue()
        self.assertEqual(output.count("[Glyphs MCP][Debug][SSE] event=message"), 2)
        self.assertEqual(output.count("detail limit reached"), 1)
        self.assertIn("sseFrames=5 logged=2 omitted=3 pingsSuppressed=0", output)
        detail_lines = [
            line
            for line in output.splitlines()
            if "[Glyphs MCP][Debug][SSE] event=" in line
        ]
        self.assertTrue(all(len(line) < 140 for line in detail_lines))

    def test_fragmented_oversized_frame_uses_bounded_parser_memory(self) -> None:
        from debug_event_logging import set_enabled

        set_enabled(True)
        chunks = [
            b"event: mes",
            b"sage\nid: 42\ndata: " + (b"x" * 5000),
            b"\n\n",
        ]
        debug = io.StringIO()
        with self._client(
            chunks,
            sink=debug,
            max_sse_excerpt_chars=16,
            max_sse_line_bytes=64,
        ) as client:
            response = client.get("/sse")

        self.assertEqual(response.status_code, 200)
        output = debug.getvalue()
        self.assertIn("event=message", output)
        self.assertIn("id=42", output)
        self.assertIn("data='xxxxxxxxxxxxxxxx…'", output)
        self.assertLess(len(output), 1000)

    def test_default_sink_is_not_replaced_by_tool_output_redirection(self) -> None:
        import debug_event_logging

        debug_event_logging.set_enabled(True)
        debug = io.StringIO()
        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()
        with mock.patch.object(debug_event_logging, "_DEFAULT_LOG_STREAM", debug):
            with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
                with self._client() as client:
                    response = client.get("/sse")
                print("spacing summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured_stdout.getvalue(), "spacing summary\n")
        self.assertEqual(captured_stderr.getvalue(), "")
        self.assertIn("[Glyphs MCP][Debug]", debug.getvalue())
        self.assertNotIn("spacing summary", debug.getvalue())

    def test_default_budget_stays_below_six_kilobytes(self) -> None:
        from debug_event_logging import set_enabled

        set_enabled(True)
        chunks = [
            b"event: message\ndata: " + (b"x" * 2000) + b"\n\n"
            for _index in range(20)
        ]
        debug = io.StringIO()
        with self._client(chunks, sink=debug) as client:
            response = client.get("/sse")

        self.assertEqual(response.status_code, 200)
        output = debug.getvalue()
        self.assertLess(len(output.encode("utf-8")), 6 * 1024)
        self.assertIn("sseFrames=20 logged=8 omitted=12 pingsSuppressed=0", output)


if __name__ == "__main__":
    unittest.main()
