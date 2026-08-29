"""Synthetic scale acceptance for generic reads, previews, and transactions."""

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


def _scale_model() -> dict:
    masters = [{"id": "m{}".format(index)} for index in range(5)]
    glyphs = {}
    for index in range(225):
        name = "g{:03d}".format(index)
        glyphs[name] = {
            "name": name,
            "id": "id_{}".format(name),
            "unicode": "{:04X}".format(0xE000 + index),
            "export": True,
            "layers": [
                {
                    "id": master["id"],
                    "masterId": master["id"],
                    "isMasterLayer": True,
                    "width": 500,
                    "leftMetricsKey": None,
                    "rightMetricsKey": None,
                    "widthMetricsKey": None,
                    "anchors": [],
                    "shapes": [],
                }
                for master in masters
            ],
        }
    return {
        "font": {"familyName": "Synthetic Scale", "upm": 1000},
        "masters": masters,
        "instances": [],
        "glyphs": glyphs,
        "kerning": {"ltr": {"m0": {}}, "rtl": {}, "vertical": {}, "context": {}},
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


class _ScaleHost:
    def __init__(self) -> None:
        self.model = _scale_model()
        self.apply_calls = 0
        self.restore_calls = 0

    def capture_model(self, _document_id: str) -> dict:
        return copy.deepcopy(self.model)

    def apply_change_set(self, _document_id: str, change_set) -> None:
        self.apply_calls += 1
        self.model = change_set.apply(self.model)

    def restore_model(self, _document_id: str, model: dict) -> None:
        self.restore_calls += 1
        self.model = copy.deepcopy(model)


class V2ScaleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.host = _ScaleHost()
        self.app = GlyphsMCPApplication(self.host)

    @staticmethod
    def _bytes(response: dict) -> int:
        return len(json.dumps(response, separators=(",", ":")).encode("utf-8"))

    def _preview_apply(self, operations: list[dict], reason: str) -> tuple[dict, dict]:
        before = fingerprint_model(self.host.model)
        preview = self.app.invoke(
            "preview_change",
            {
                "documentId": "doc_scale",
                "expectedDocumentFingerprint": before,
                "operations": operations,
                "constraints": [],
            },
        ).to_dict()
        self.assertTrue(preview["ok"], preview)
        applied = self.app.invoke(
            "apply_change",
            {
                "documentId": "doc_scale",
                "previewId": preview["data"]["previewId"],
                "expectedDocumentFingerprint": before,
                "reason": reason,
            },
        ).to_dict()
        self.assertTrue(applied["ok"], applied)
        return preview, applied

    def test_200_glyph_and_178_kerning_entries_each_apply_once(self) -> None:
        _, glyphs = self._preview_apply(
            [
                {
                    "op": "set",
                    "target": {
                        "entity": "glyph",
                        "ids": ["g{:03d}".format(index) for index in range(200)],
                    },
                    "field": "export",
                    "value": False,
                }
            ],
            "set 200 exact glyph fields",
        )
        self.assertEqual(glyphs["data"]["observedChangeCount"], 200)
        self.assertEqual(glyphs["data"]["transactionCount"], 1)
        self.assertEqual(self.host.apply_calls, 1)

        operations = [
            {
                "op": "insert",
                "target": {"entity": "document", "ids": ["document"]},
                "field": "kerning.ltr.m0",
                "newId": "g{:03d}".format(index),
                "value": {"g{:03d}".format(index + 1): -20},
            }
            for index in range(178)
        ]
        _, kerning = self._preview_apply(operations, "insert 178 exact kerning entries")
        self.assertEqual(kerning["data"]["observedChangeCount"], 178)
        self.assertEqual(kerning["data"]["transactionCount"], 1)
        self.assertEqual(self.host.apply_calls, 2)

    def test_generic_read_pages_remain_bounded_at_1125_layers(self) -> None:
        glyphs = self.app.invoke(
            "read_document",
            {
                "documentId": "doc_scale",
                "selector": {"entity": "glyph", "pageSize": 100},
                "projection": {"fields": ["id", "name", "unicode", "export"]},
            },
        ).to_dict()
        self.assertEqual(glyphs["data"]["selectedCount"], 225)
        self.assertEqual(len(glyphs["data"]["items"]), 100)
        self.assertLess(self._bytes(glyphs), 64 * 1024)

        layers = self.app.invoke(
            "read_document",
            {
                "documentId": "doc_scale",
                "selector": {"entity": "layer", "pageSize": 100},
                "projection": {"fields": ["id", "width", "spacing.horizontal"]},
            },
        ).to_dict()
        self.assertEqual(layers["data"]["selectedCount"], 1125)
        self.assertEqual(len(layers["data"]["items"]), 100)
        self.assertLess(self._bytes(layers), 64 * 1024)

    def test_200_layer_operations_preview_once_apply_once_and_revert_once(self) -> None:
        operations = [
            {
                "op": "set",
                "target": {
                    "entity": "layer",
                    "ids": ["m{}".format(master_index)],
                    "parent": {"glyphName": "g{:03d}".format(glyph_index)},
                },
                "field": "leftMetricsKey",
                "value": "=H",
            }
            for glyph_index in range(40)
            for master_index in range(5)
        ]
        preview, applied = self._preview_apply(
            operations, "set 200 exact layer metrics keys"
        )
        self.assertEqual(preview["data"]["normalizedOperationCount"], 200)
        self.assertTrue(preview["data"]["normalizedOperationsTruncated"])
        self.assertEqual(applied["data"]["observedChangeCount"], 200)
        self.assertEqual(self.host.apply_calls, 1)
        self.assertLess(self._bytes(preview), 64 * 1024)
        self.assertLess(self._bytes(applied), 64 * 1024)

        reverted = self.app.invoke(
            "revert_change",
            {
                "documentId": "doc_scale",
                "operationId": applied["data"]["operationId"],
                "expectedDocumentFingerprint": fingerprint_model(self.host.model),
            },
        ).to_dict()
        self.assertTrue(reverted["ok"], reverted)
        self.assertEqual(self.host.apply_calls, 2)

    def test_selector_cursor_is_bound_to_entity_projection_and_schema(self) -> None:
        first = self.app.invoke(
            "read_document",
            {
                "documentId": "doc_scale",
                "selector": {"entity": "glyph", "pageSize": 1},
                "projection": {"fields": ["name"]},
            },
        ).to_dict()
        cursor = first["page"]["nextCursor"]
        crossed_entity = self.app.invoke(
            "read_document",
            {
                "documentId": "doc_scale",
                "selector": {"entity": "master", "pageSize": 1, "cursor": cursor},
                "projection": {"fields": ["name"]},
            },
        ).to_dict()
        crossed_projection = self.app.invoke(
            "read_document",
            {
                "documentId": "doc_scale",
                "selector": {"entity": "glyph", "pageSize": 1, "cursor": cursor},
                "projection": {"fields": ["name", "unicode"]},
            },
        ).to_dict()
        self.assertEqual(crossed_entity["error"]["code"], "invalid_cursor")
        self.assertEqual(crossed_projection["error"]["code"], "invalid_cursor")

    def test_full_mcp_discovery_payload_is_below_96_kib(self) -> None:
        server = create_server(self.app)

        async def measure() -> int:
            async with Client(server) as client:
                tools = await client.list_tools()
                payload = [
                    tool.model_dump(by_alias=True, exclude_none=True) for tool in tools
                ]
                return len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

        self.assertLessEqual(asyncio.run(measure()), (96 - 8) * 1024)


if __name__ == "__main__":
    unittest.main()
