"""Synthetic scale acceptance for the v2 catalog and transaction kernel."""

from __future__ import annotations

import asyncio
import copy
import json
import sys
import unittest
from pathlib import Path

from fastmcp import Client


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.semantic import fingerprint_model  # noqa: E402
from glyphs_mcp_v2.transport.fastmcp import create_server  # noqa: E402


def _scale_model():
    masters = [{"id": "m{}".format(index)} for index in range(5)]
    glyphs = {}
    for index in range(225):
        name = "g{:03d}".format(index)
        glyphs[name] = {
            "name": name,
            "id": "id_{}".format(name),
            "category": "Letter",
            "subCategory": "Uppercase",
            "unicode": "{:04X}".format(0xE000 + index),
            "export": True,
            "mastersCompatible": True,
            "layers": {
                master["id"]: {
                    "width": 500,
                    "anchors": {},
                    "components": [],
                    "pathSignature": [4],
                }
                for master in masters
            },
        }
    return {
        "font": {"familyName": "Synthetic Scale", "upm": 1000},
        "masters": masters,
        "instances": [],
        "glyphs": glyphs,
        "kerning": {},
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


class _ScaleHost:
    def __init__(self):
        self.model = _scale_model()
        self.apply_calls = 0
        self.restore_calls = 0

    def capture_model(self, document_id):
        return copy.deepcopy(self.model)

    def apply_change_set(self, document_id, change_set):
        self.apply_calls += 1
        self.model = change_set.apply(self.model)

    def restore_model(self, document_id, model):
        self.restore_calls += 1
        self.model = copy.deepcopy(model)


class V2ScaleTests(unittest.TestCase):
    def setUp(self):
        self.host = _ScaleHost()
        self.app = GlyphsMCPApplication(self.host)

    @staticmethod
    def _bytes(response):
        return len(json.dumps(response, separators=(",", ":")).encode("utf-8"))

    def test_200_glyph_and_178_pair_batches_each_apply_once(self) -> None:
        glyph_review = self.app.invoke(
            "review_glyph_updates",
            {
                "documentId": "doc_scale",
                "updates": [
                    {"glyphName": "g{:03d}".format(index), "export": False}
                    for index in range(200)
                ],
            },
        ).to_dict()
        self.assertEqual(glyph_review["data"]["changeSet"]["changeCount"], 200)
        glyph_apply = self.app.invoke(
            "apply_glyph_updates",
            {"reviewId": glyph_review["data"]["reviewId"], "confirm": True},
        ).to_dict()
        self.assertTrue(glyph_apply["ok"])
        self.assertEqual(glyph_apply["data"]["transactionCount"], 1)
        self.assertEqual(self.host.apply_calls, 1)

        kerning_review = self.app.invoke(
            "review_kerning_updates",
            {
                "documentId": "doc_scale",
                "updates": [
                    {
                        "masterId": "m0",
                        "left": "g{:03d}".format(index),
                        "right": "g{:03d}".format(index + 1),
                        "value": -20,
                    }
                    for index in range(178)
                ],
            },
        ).to_dict()
        self.assertEqual(kerning_review["data"]["changeSet"]["changeCount"], 178)
        kerning_apply = self.app.invoke(
            "apply_kerning_updates",
            {"reviewId": kerning_review["data"]["reviewId"], "confirm": True},
        ).to_dict()
        self.assertTrue(kerning_apply["ok"])
        self.assertEqual(kerning_apply["data"]["transactionCount"], 1)
        self.assertEqual(self.host.apply_calls, 2)

    def test_spacing_and_list_pages_remain_bounded(self) -> None:
        glyphs = self.app.invoke(
            "list_glyphs", {"documentId": "doc_scale", "pageSize": 500}
        ).to_dict()
        self.assertLess(self._bytes(glyphs), 64 * 1024)
        self.assertNotIn("layers", glyphs["data"]["glyphs"][0])
        self.assertNotIn("glyphsLink", glyphs["data"]["glyphs"][0])

        spacing = self.app.invoke(
            "review_spacing", {"documentId": "doc_scale"}
        ).to_dict()
        self.assertTrue(spacing["ok"])
        self.assertEqual(spacing["data"]["simulation"]["actionableCount"], 0)
        self.assertEqual(spacing["data"]["simulation"]["maxIterations"], 5)
        self.assertLess(self._bytes(spacing), 64 * 1024)

    def test_document_cursor_cannot_cross_operation_or_projection_scope(self) -> None:
        self.host.model["kerning"] = [
            {
                "masterId": "m0",
                "left": {"kind": "glyph", "id": "id_g000", "name": "g000"},
                "right": {"kind": "glyph", "id": "id_g001", "name": "g001"},
                "value": -20,
            }
            for _index in range(10)
        ]
        glyph_page = self.app.invoke(
            "list_glyphs", {"documentId": "doc_scale", "pageSize": 1}
        ).to_dict()
        cursor = glyph_page["page"]["nextCursor"]

        crossed_operation = self.app.invoke(
            "list_kerning_pairs",
            {"documentId": "doc_scale", "pageSize": 1, "cursor": cursor},
        ).to_dict()
        crossed_projection = self.app.invoke(
            "list_glyphs",
            {
                "documentId": "doc_scale",
                "pageSize": 1,
                "fields": ["name", "unicode"],
                "cursor": cursor,
            },
        ).to_dict()

        self.assertEqual(crossed_operation["error"]["code"], "invalid_cursor")
        self.assertEqual(crossed_projection["error"]["code"], "invalid_cursor")

    def test_full_mcp_discovery_payload_is_below_96_kib(self) -> None:
        server = create_server(self.app)

        async def measure():
            async with Client(server) as client:
                tools = await client.list_tools()
                payload = [tool.model_dump(by_alias=True, exclude_none=True) for tool in tools]
                return len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

        self.assertLess(asyncio.run(measure()), 96 * 1024)


if __name__ == "__main__":
    unittest.main()
