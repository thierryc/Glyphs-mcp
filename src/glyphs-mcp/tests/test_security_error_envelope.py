"""Tests for McpErrorEnvelopeMiddleware (protocol-safety error handling)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


class McpErrorEnvelopeMiddlewareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))

    def _client(self):
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
        from starlette.testclient import TestClient

        from security import McpErrorEnvelopeMiddleware

        async def err_no_content_type(request):
            return Response("boom", status_code=400)

        async def err_plain_text(request):
            return PlainTextResponse("Forbidden", status_code=403)

        async def err_with_session_id(request):
            return Response(
                "Missing session ID",
                status_code=400,
                headers={"mcp-session-id": "abc123"},
            )

        async def err_no_valid_session_id(request):
            return Response("Bad Request: No valid session ID provided", status_code=400)

        async def err_missing_session_id(request):
            return Response("Bad Request: Missing session ID", status_code=400)

        async def ok_mcp_post(request):
            return JSONResponse({"ok": True})

        async def sse(request):
            async def iterator():
                yield b"data: hi\n\n"

            return StreamingResponse(iterator(), media_type="text/event-stream")

        async def raiser(request):
            raise RuntimeError("kaboom")

        app = Starlette(middleware=[Middleware(McpErrorEnvelopeMiddleware)])
        app.add_route("/err-no-ct", err_no_content_type, methods=["GET"])
        app.add_route("/err-plain", err_plain_text, methods=["GET"])
        app.add_route("/err-session", err_with_session_id, methods=["GET"])
        app.add_route("/mcp/", ok_mcp_post, methods=["POST"])
        app.add_route("/mcp/stale", err_no_valid_session_id, methods=["POST"])
        app.add_route("/mcp/missing", err_missing_session_id, methods=["POST"])
        app.add_route("/sse", sse, methods=["GET"])
        app.add_route("/raise", raiser, methods=["GET"])
        return TestClient(app)

    def test_wraps_error_without_content_type_as_json(self) -> None:
        with self._client() as client:
            res = client.get("/err-no-ct", headers={"accept": "application/json"})

        self.assertEqual(res.status_code, 400)
        self.assertIn("application/json", res.headers.get("content-type", ""))
        payload = res.json()
        self.assertEqual(payload.get("jsonrpc"), "2.0")
        self.assertIn("error", payload)
        self.assertEqual(payload["error"]["data"]["httpStatus"], 400)
        self.assertIn("howToFix", payload["error"]["data"])
        self.assertIn("expectedAccept", payload["error"]["data"])

    def test_wraps_plain_text_errors_as_json(self) -> None:
        with self._client() as client:
            res = client.get("/err-plain")

        self.assertEqual(res.status_code, 403)
        self.assertIn("application/json", res.headers.get("content-type", ""))
        payload = res.json()
        self.assertEqual(payload["error"]["data"]["httpStatus"], 403)
        self.assertIn("Forbidden", payload["error"]["data"]["detail"])

    def test_preserves_mcp_session_id_header(self) -> None:
        with self._client() as client:
            res = client.get("/err-session")

        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.headers.get("mcp-session-id"), "abc123")
        self.assertIn("application/json", res.headers.get("content-type", ""))

    def test_does_not_override_sse(self) -> None:
        with self._client() as client:
            res = client.get("/sse", headers={"accept": "text/event-stream"})

        self.assertEqual(res.status_code, 200)
        self.assertIn("text/event-stream", res.headers.get("content-type", ""))
        self.assertIn("data: hi", res.text)

    def test_exception_becomes_json_500(self) -> None:
        with self._client() as client:
            res = client.get("/raise")

        self.assertEqual(res.status_code, 500)
        self.assertIn("application/json", res.headers.get("content-type", ""))
        payload = res.json()
        self.assertEqual(payload["error"]["data"]["httpStatus"], 500)
        self.assertIn("kaboom", payload["error"]["data"]["detail"])

    def test_post_without_session_id_passes_through(self) -> None:
        with self._client() as client:
            res = client.post("/mcp/", headers={"accept": "application/json"}, json={"jsonrpc": "2.0"})

        self.assertEqual(res.status_code, 200)
        self.assertIn("application/json", res.headers.get("content-type", ""))
        payload = res.json()
        self.assertTrue(payload.get("ok"))

    def test_stale_session_400_is_normalized_to_404(self) -> None:
        with self._client() as client:
            res = client.post(
                "/mcp/stale",
                headers={"mcp-session-id": "stale"},
                json={"jsonrpc": "2.0"},
            )

        self.assertEqual(res.status_code, 404)
        self.assertIn("application/json", res.headers.get("content-type", ""))
        payload = res.json()
        self.assertEqual(payload["error"]["data"]["httpStatus"], 404)
        self.assertIn("Session expired", payload["error"]["message"])

    def test_missing_session_id_stays_400(self) -> None:
        with self._client() as client:
            res = client.post("/mcp/missing", json={"jsonrpc": "2.0"})

        self.assertEqual(res.status_code, 400)
        self.assertIn("application/json", res.headers.get("content-type", ""))
        payload = res.json()
        self.assertEqual(payload["error"]["data"]["httpStatus"], 400)

    def test_healthz_is_available_and_json(self) -> None:
        with self._client() as client:
            res = client.get("/healthz")

        self.assertEqual(res.status_code, 200)
        self.assertIn("application/json", res.headers.get("content-type", ""))
        payload = res.json()
        self.assertTrue(payload.get("ok"))
        self.assertIn("version", payload)
        self.assertIn("glyphsReachable", payload)

    def test_mcp_path_normalizer_avoids_post_redirect(self) -> None:
        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.responses import JSONResponse
        from starlette.testclient import TestClient

        from security import McpNormalizeMcpPathMiddleware

        async def handler(request):
            return JSONResponse({"ok": True})

        inner = Starlette()
        inner.add_route("/", handler, methods=["POST"])

        outer = Starlette(middleware=[Middleware(McpNormalizeMcpPathMiddleware)])
        outer.mount("/mcp/", inner)

        with TestClient(outer) as client:
            res = client.request(
                "POST",
                "/mcp",
                json={"ping": True},
                follow_redirects=False,
            )

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("ok"))


if __name__ == "__main__":
    unittest.main()
