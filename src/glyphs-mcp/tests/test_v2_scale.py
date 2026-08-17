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
from glyphs_mcp_v2.audit import AuditLog  # noqa: E402
from glyphs_mcp_v2.change_review import resolve_outline_overlay  # noqa: E402
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
        self.fail_next_apply = False

    def capture_model(self, document_id):
        return copy.deepcopy(self.model)

    def apply_change_set(self, document_id, change_set):
        self.apply_calls += 1
        self.model = change_set.apply(self.model)
        if self.fail_next_apply:
            self.fail_next_apply = False
            self.model["font"]["familyName"] = "Corrupted readback"
            raise RuntimeError("synthetic apply failure")

    def restore_model(self, document_id, model):
        self.restore_calls += 1
        self.model = copy.deepcopy(model)


class V2ScaleTests(unittest.TestCase):
    def setUp(self):
        self.host = _ScaleHost()
        self.audit = AuditLog()
        self.app = GlyphsMCPApplication(self.host, audit=self.audit)

    @staticmethod
    def _bytes(response):
        return len(json.dumps(response, separators=(",", ":")).encode("utf-8"))

    def test_200_glyph_and_178_pair_batches_each_apply_once(self) -> None:
        before_glyphs = fingerprint_model(self.host.model)
        glyph_apply = self.app.invoke(
            "apply_glyph_updates",
            {
                "documentId": "doc_scale",
                "expectedDocumentFingerprint": before_glyphs,
                "reason": "Scale-test direct glyph batch",
                "updates": [
                    {"glyphName": "g{:03d}".format(index), "export": False}
                    for index in range(200)
                ],
            },
        ).to_dict()
        self.assertTrue(glyph_apply["ok"])
        self.assertNotIn("reviewId", glyph_apply["data"])
        self.assertEqual(glyph_apply["data"]["changeCount"], 200)
        self.assertEqual(glyph_apply["data"]["transactionCount"], 1)
        self.assertEqual(glyph_apply["operationId"], glyph_apply["data"]["operationId"])
        self.assertEqual(self.host.apply_calls, 1)

        before_kerning = fingerprint_model(self.host.model)
        kerning_apply = self.app.invoke(
            "apply_kerning_updates",
            {
                "documentId": "doc_scale",
                "expectedDocumentFingerprint": before_kerning,
                "reason": "Scale-test direct kerning batch",
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
        self.assertTrue(kerning_apply["ok"])
        self.assertNotIn("reviewId", kerning_apply["data"])
        self.assertEqual(kerning_apply["data"]["changeCount"], 178)
        self.assertEqual(kerning_apply["data"]["transactionCount"], 1)
        self.assertEqual(kerning_apply["operationId"], kerning_apply["data"]["operationId"])
        self.assertEqual(self.host.apply_calls, 2)

        operation = self.app.invoke(
            "get_operation",
            {"operationId": kerning_apply["operationId"], "pageSize": 100},
        ).to_dict()
        self.assertTrue(operation["ok"])
        self.assertEqual(operation["operationId"], kerning_apply["operationId"])
        self.assertEqual(operation["data"]["operationId"], kerning_apply["operationId"])
        self.assertEqual(operation["data"]["payload"]["status"], "applied")
        self.assertLess(self._bytes(operation), 64 * 1024)
        events = self.audit.list_events(document_id="doc_scale")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].details["operationId"], glyph_apply["operationId"])
        self.assertEqual(events[1].details["operationId"], kerning_apply["operationId"])

    def test_direct_apply_rejects_a_stale_fingerprint_without_mutating(self) -> None:
        response = self.app.invoke(
            "apply_glyph_updates",
            {
                "documentId": "doc_scale",
                "expectedDocumentFingerprint": "stale",
                "updates": [{"glyphName": "g000", "export": False}],
            },
        ).to_dict()

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "stale_document")
        self.assertEqual(self.host.apply_calls, 0)
        self.assertEqual(len(self.audit.list_events(document_id="doc_scale")), 1)

    def test_change_operation_preserves_requested_glyph_order(self) -> None:
        response = self.app.invoke(
            "apply_glyph_updates",
            {
                "documentId": "doc_scale",
                "expectedDocumentFingerprint": fingerprint_model(self.host.model),
                "updates": [
                    {"glyphName": "g010", "export": False},
                    {"glyphName": "g002", "export": False},
                ],
            },
        ).to_dict()
        operation = self.app.invoke(
            "get_operation", {"operationId": response["operationId"]}
        ).to_dict()

        self.assertEqual(
            [item["glyphName"] for item in operation["data"]["payload"]["changes"]],
            ["g010", "g002"],
        )

    def test_topology_compatible_apply_registers_private_outline_snapshots(self) -> None:
        before_paths = [
            {
                "closed": True,
                "nodes": [
                    {"x": 0, "y": 0, "type": "line"},
                    {"x": 100, "y": 0, "type": "line"},
                ],
            }
        ]
        after_paths = copy.deepcopy(before_paths)
        after_paths[0]["nodes"][1]["x"] = 120
        layer = self.host.model["glyphs"]["g000"]["layers"]["m0"]
        layer["paths"] = before_paths

        response = self.app.invoke(
            "apply_compatibility_updates",
            {
                "documentId": "doc_scale",
                "expectedDocumentFingerprint": fingerprint_model(self.host.model),
                "updates": [
                    {"glyphName": "g000", "masterId": "m0", "paths": after_paths}
                ],
            },
        ).to_dict()
        operation = self.app._change_reviews.get(response["operationId"])

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["visualizableGlyphCount"], 1)
        visual_items = [item for item in operation.items if item.get("displayBefore")]
        self.assertEqual(len(visual_items), 1)
        self.assertEqual(visual_items[0]["displayBefore"], before_paths)
        self.assertEqual(visual_items[0]["displayApplied"], after_paths)

        public = self.app.invoke(
            "get_operation", {"operationId": response["operationId"]}
        ).to_dict()
        self.assertNotIn("displayBefore", public["data"]["payload"]["changes"][0])
        self.assertNotIn("displayApplied", public["data"]["payload"]["changes"][0])

    def test_change_operation_rollback_is_verified_and_updates_review_state(self) -> None:
        before_paths = [
            {
                "closed": True,
                "nodes": [
                    {"x": 0, "y": 0, "type": "line"},
                    {"x": 100, "y": 0, "type": "line"},
                ],
            }
        ]
        after_paths = copy.deepcopy(before_paths)
        after_paths[0]["nodes"][1]["x"] = 120
        self.host.model["glyphs"]["g000"]["layers"]["m0"]["paths"] = before_paths
        before_fingerprint = fingerprint_model(self.host.model)
        applied = self.app.invoke(
            "apply_compatibility_updates",
            {
                "documentId": "doc_scale",
                "expectedDocumentFingerprint": before_fingerprint,
                "updates": [{"glyphName": "g000", "masterId": "m0", "paths": after_paths}],
            },
        ).to_dict()
        operation_id = applied["operationId"]
        operation = self.app._change_reviews.get(operation_id)
        overlay = resolve_outline_overlay(
            operation,
            glyph_name="g000",
            layer_id="m0",
            master_id="m0",
            live_paths=after_paths,
        )
        self.assertFalse(overlay["stale"])

        rolled_back = self.app.invoke(
            "rollback_change_operation",
            {
                "operationId": operation_id,
                "expectedDocumentFingerprint": applied["data"]["afterFingerprint"],
            },
        ).to_dict()

        self.assertTrue(rolled_back["ok"])
        self.assertEqual(rolled_back["operationId"], operation_id)
        self.assertEqual(rolled_back["data"]["status"], "rolled_back")
        self.assertEqual(rolled_back["data"]["afterFingerprint"], before_fingerprint)
        self.assertEqual(fingerprint_model(self.host.model), before_fingerprint)
        self.assertEqual(self.host.apply_calls, 2)
        self.assertEqual(len(self.audit.list_events(document_id="doc_scale")), 2)
        updated = self.app._change_reviews.get(operation_id)
        self.assertEqual(updated.status, "rolled_back")
        self.assertIsNone(
            resolve_outline_overlay(
                updated,
                glyph_name="g000",
                layer_id="m0",
                master_id="m0",
                live_paths=before_paths,
            )
        )
        public = self.app.invoke("get_operation", {"operationId": operation_id}).to_dict()
        self.assertEqual(public["data"]["payload"]["status"], "rolled_back")

    def test_change_operation_rollback_rejects_later_edits_and_marks_stale(self) -> None:
        applied = self.app.invoke(
            "apply_glyph_updates",
            {
                "documentId": "doc_scale",
                "expectedDocumentFingerprint": fingerprint_model(self.host.model),
                "updates": [{"glyphName": "g000", "export": False}],
            },
        ).to_dict()
        self.host.model["glyphs"]["g001"]["export"] = False

        rejected = self.app.invoke(
            "rollback_change_operation",
            {
                "operationId": applied["operationId"],
                "expectedDocumentFingerprint": applied["data"]["afterFingerprint"],
            },
        ).to_dict()

        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["code"], "stale_document")
        self.assertEqual(self.host.apply_calls, 1)
        self.assertEqual(
            self.app._change_reviews.get(applied["operationId"]).status,
            "stale",
        )
        public = self.app.invoke(
            "get_operation", {"operationId": applied["operationId"]}
        ).to_dict()
        self.assertEqual(public["data"]["payload"]["status"], "stale")
        self.assertEqual(len(self.audit.list_events(document_id="doc_scale")), 2)

    def test_failed_change_operation_rollback_restores_pre_rollback_state(self) -> None:
        applied = self.app.invoke(
            "apply_glyph_updates",
            {
                "documentId": "doc_scale",
                "expectedDocumentFingerprint": fingerprint_model(self.host.model),
                "updates": [{"glyphName": "g000", "export": False}],
            },
        ).to_dict()
        verified_after = copy.deepcopy(self.host.model)
        self.host.fail_next_apply = True

        failed = self.app.invoke(
            "rollback_change_operation",
            {
                "operationId": applied["operationId"],
                "expectedDocumentFingerprint": applied["data"]["afterFingerprint"],
            },
        ).to_dict()

        self.assertFalse(failed["ok"])
        self.assertEqual(failed["error"]["code"], "rollback_failed")
        self.assertTrue(failed["data"]["preRollbackStateRestored"])
        self.assertEqual(self.host.model, verified_after)
        self.assertEqual(self.host.restore_calls, 1)
        self.assertEqual(
            self.app._change_reviews.get(applied["operationId"]).status,
            "applied",
        )
        self.assertEqual(len(self.audit.list_events(document_id="doc_scale")), 2)

    def test_225_glyph_five_master_spacing_batch_applies_once_and_converges(self) -> None:
        before = fingerprint_model(self.host.model)
        items = [
            {
                "glyphName": "g{:03d}".format(glyph_index),
                "masterId": "m{}".format(master_index),
                "width": 500,
                "targetWidth": 520,
                "category": "Letter",
            }
            for glyph_index in range(225)
            for master_index in range(5)
        ]

        applied = self.app.invoke(
            "apply_spacing",
            {
                "documentId": "doc_scale",
                "expectedDocumentFingerprint": before,
                "reason": "Five-master spacing scale gate",
                "items": items,
            },
        ).to_dict()

        self.assertTrue(applied["ok"])
        self.assertEqual(applied["data"]["changeCount"], 1125)
        self.assertEqual(applied["data"]["affectedGlyphCount"], 225)
        self.assertEqual(applied["data"]["transactionCount"], 1)
        self.assertEqual(self.host.apply_calls, 1)
        self.assertEqual(len(self.audit.list_events(document_id="doc_scale")), 1)
        self.assertLess(self._bytes(applied), 64 * 1024)

        converged = self.app.invoke(
            "review_spacing", {"documentId": "doc_scale"}
        ).to_dict()
        self.assertTrue(converged["ok"])
        self.assertEqual(converged["data"]["changeCount"], 0)
        self.assertEqual(converged["data"]["simulation"]["actionableCount"], 0)

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
