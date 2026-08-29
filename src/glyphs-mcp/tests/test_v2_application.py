"""Application-service tests for the generic Glyphs MCP v2 surface."""

from __future__ import annotations

import copy
import sys
import time
import unittest
from pathlib import Path

from jsonschema import validate


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.activity import OperationActivityStore  # noqa: E402
from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.contracts import ToolResponse  # noqa: E402
from glyphs_mcp_v2.ports import (  # noqa: E402
    FontSnapshot,
    HostAccessError,
    HostRuntimeSnapshot,
)


def _model() -> dict:
    return {
        "font": {
            "familyName": "Alpha",
            "upm": 1000,
            "grid": 1,
            "gridSubDivision": 1,
        },
        "masters": [{"id": "m1", "name": "Regular", "axes": []}],
        "instances": [],
        "glyphs": {
            name: {
                "id": "g{}".format(name),
                "name": name,
                "category": "Letter",
                "layers": [
                    {
                        "id": "{}-m1".format(name),
                        "masterId": "m1",
                        "name": "Regular",
                        "roles": ["master"],
                        "isMasterLayer": True,
                        "isSpecialLayer": False,
                        "width": 500,
                        "anchors": [],
                        "shapes": [],
                    }
                ],
            }
            for name in ("A", "B")
        },
        "kerning": {},
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


class _FakeHost:
    def __init__(self) -> None:
        self.documents = (
            FontSnapshot(
                document_id="doc_alpha",
                legacy_index=0,
                family_name="Alpha",
                file_path="/tmp/Alpha.glyphs",
                has_unsaved_changes=False,
                active=True,
                master_count=1,
                instance_count=0,
                glyph_count=2,
                units_per_em=1000,
                version_major=1,
                version_minor=0,
                format_version=3,
                last_saved_app_version="4004",
            ),
        )
        self.model = _model()
        self.opened = []
        self.repair_calls = []

    def runtime_snapshot(self) -> HostRuntimeSnapshot:
        return HostRuntimeSnapshot(
            application="Glyphs",
            application_version="4.0",
            build_number="4004",
            python_version="3.12.3",
            open_document_count=1,
        )

    def list_documents(self):
        return self.documents

    def capture_model(self, _document_id):
        return copy.deepcopy(self.model)

    def capture_source_file_state(self, _document_id, include_model=False):
        state = {
            "kind": "glyphs",
            "exists": True,
            "readable": True,
            "contentFingerprint": "sha256:" + "a" * 64,
            "filePath": "/tmp/Alpha.glyphs",
        }
        if include_model:
            state["savedModel"] = copy.deepcopy(self.model)
        return state

    def scripting_runtime_safety_status(self):
        return {
            "state": "healthy",
            "mode": "strict",
            "strictInterlockAvailable": True,
            "livePythonAvailable": True,
            "stagedPythonAvailable": True,
            "automaticRepairAvailable": False,
            "incidentId": None,
            "affectedSlotCount": 0,
            "nextAction": "none",
            "activeExecutionId": None,
            "currentIncident": None,
            "lastRepair": None,
            "recentTransitions": [],
        }

    def repair_scripting_runtime(self, *, expected_incident_id=None, trigger="agent"):
        self.repair_calls.append((expected_incident_id, trigger))
        return {
            "repair": {
                "result": "not_needed",
                "trigger": trigger,
                "beforeState": "healthy",
                "afterState": "healthy",
            },
            "scriptingRuntimeSafety": self.scripting_runtime_safety_status(),
        }

    def open_edit_tab(self, document_id, glyph_names, *, master_id=None):
        self.opened.append((document_id, tuple(glyph_names), master_id))


class V2ApplicationTests(unittest.TestCase):
    def test_server_info_declares_generic_registries_and_permanent_python(self) -> None:
        payload = GlyphsMCPApplication(_FakeHost()).invoke(
            "get_server_info"
        ).to_dict()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["apiMajor"], 2)
        self.assertIn("permanent_python_fallback", payload["data"]["capabilities"])
        self.assertIn("save_tolerant_transactions", payload["data"]["capabilities"])
        self.assertIn("detached_read_only_python", payload["data"]["capabilities"])
        self.assertEqual(
            payload["data"]["registries"]["pythonModes"],
            ["read_only", "staged_document", "live_open_world"],
        )
        self.assertEqual(
            set(payload["data"]["registries"]["changeOperations"]),
            {"set", "translate", "insert", "remove", "move", "duplicate"},
        )
        self.assertFalse(payload["data"]["knowledge"]["runtimeNetworkRequired"])
        identity = payload["data"]["runtimeIdentity"]
        self.assertEqual(identity["version"], "2.0.0")
        self.assertRegex(identity["runtimeId"], r"^2\.0\.0\+[0-9a-f]{12}$")
        self.assertRegex(identity["codeHash"], r"^[0-9a-f]{64}$")
        validate(payload, TOOL_CATALOG["get_server_info"].output_schema)

    def test_list_documents_uses_stable_normative_ids(self) -> None:
        payload = GlyphsMCPApplication(_FakeHost()).invoke(
            "list_documents"
        ).to_dict()
        document = payload["data"]["documents"][0]

        self.assertEqual(document["documentId"], "doc_alpha")
        self.assertEqual(document["legacyIndex"], 0)
        self.assertTrue(document["hasFilePath"])
        self.assertFalse(document["hasUnsavedChanges"])
        validate(payload, TOOL_CATALOG["list_documents"].output_schema)

    def test_read_document_relations_and_selector_pagination_are_bound(self) -> None:
        app = GlyphsMCPApplication(_FakeHost())
        selector = {
            "entity": "glyph",
            "pageSize": 1,
            "relations": [
                {
                    "name": "layers",
                    "selector": {"entity": "layer", "pageSize": 10},
                    "projection": {"fields": ["id", "masterId", "width"]},
                }
            ],
        }
        first = app.invoke(
            "read_document",
            {
                "documentId": "doc_alpha",
                "selector": selector,
                "projection": {"fields": ["id", "name"]},
            },
        ).to_dict()
        self.assertEqual(len(first["data"]["items"]), 1)
        glyph = first["data"]["items"][0]
        layer = glyph["relations"]["layers"]["items"][0]
        self.assertEqual(layer["parent"]["glyphName"], glyph["id"])

        second_selector = {
            **selector,
            "cursor": first["page"]["nextCursor"],
        }
        second = app.invoke(
            "read_document",
            {
                "documentId": "doc_alpha",
                "selector": second_selector,
                "projection": {"fields": ["id", "name"]},
            },
        ).to_dict()
        self.assertTrue(second["ok"])
        self.assertNotEqual(
            second["data"]["items"][0]["id"], glyph["id"]
        )

    def test_generic_predicates_numeric_order_reducers_and_persistence(self) -> None:
        host = _FakeHost()
        host.model["glyphs"]["A"]["layers"][0]["width"] = 900
        host.model["glyphs"]["B"]["layers"][0]["width"] = 120
        app = GlyphsMCPApplication(host)
        selected = app.invoke(
            "read_document",
            {
                "documentId": "doc_alpha",
                "selector": {
                    "entity": "layer",
                    "predicate": {
                        "op": "gte",
                        "field": "width",
                        "value": 100,
                    },
                    "orderBy": {
                        "field": "width",
                        "type": "number",
                        "descending": True,
                    },
                },
                "projection": {
                    "fields": ["id", "width"],
                    "reducers": [
                        {"name": "count", "op": "count"},
                        {"name": "averageWidth", "op": "average", "field": "width"},
                    ],
                },
            },
        ).to_dict()

        self.assertTrue(selected["ok"])
        self.assertEqual(
            [item["values"]["width"] for item in selected["data"]["items"]],
            [900, 120],
        )
        self.assertEqual(selected["data"]["reducers"], {"count": 2, "averageWidth": 510})

        persistence = app.invoke(
            "read_document",
            {
                "documentId": "doc_alpha",
                "selector": {"entity": "document"},
                "projection": {"fields": ["persistence"]},
            },
        ).to_dict()
        state = persistence["data"]["items"][0]["values"]["persistence"]
        self.assertEqual(state["liveDocumentFingerprint"], persistence["data"]["documentFingerprint"])
        self.assertEqual(state["sourceFileFingerprint"], "sha256:" + "a" * 64)
        self.assertEqual(state["saveEpoch"], 0)
        self.assertEqual(
            state["lastSavedDocumentFingerprint"],
            state["liveDocumentFingerprint"],
        )

    def test_constraint_failures_are_evidence_not_transport_errors(self) -> None:
        payload = GlyphsMCPApplication(_FakeHost()).invoke(
            "evaluate_constraints",
            {
                "documentId": "doc_alpha",
                "constraints": [
                    {
                        "label": "wrong width",
                        "left": {
                            "kind": "field",
                            "selector": {
                                "entity": "layer",
                                "ids": ["A-m1"],
                                "parent": {"glyphName": "A"},
                            },
                            "field": "width",
                        },
                        "operator": "eq",
                        "right": {"kind": "literal", "value": 600},
                    }
                ],
            },
        ).to_dict()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "warning")
        self.assertFalse(payload["data"]["passed"])
        validate(payload, TOOL_CATALOG["evaluate_constraints"].output_schema)

    def test_runtime_status_repair_and_ui_are_explicit_boundaries(self) -> None:
        host = _FakeHost()
        app = GlyphsMCPApplication(host)
        status = app.invoke("get_runtime_status").to_dict()
        repaired = app.invoke(
            "repair_runtime", {"reason": "verify healthy interlock"}
        ).to_dict()
        opened = app.invoke(
            "open_document_view",
            {
                "documentId": "doc_alpha",
                "glyphNames": ["A", "B"],
                "masterId": "m1",
            },
        ).to_dict()

        self.assertTrue(status["ok"])
        self.assertTrue(repaired["ok"])
        self.assertEqual(host.repair_calls, [(None, "agent")])
        self.assertTrue(opened["ok"])
        self.assertEqual(host.opened, [("doc_alpha", ("A", "B"), "m1")])
        self.assertFalse(opened["data"]["documentChanged"])
        self.assertEqual(opened["tool"], "open_document_view")

    def test_host_failures_are_normalized_without_transport_exceptions(self) -> None:
        class BrokenHost(_FakeHost):
            def list_documents(self):
                raise HostAccessError("Glyphs is busy")

        payload = GlyphsMCPApplication(BrokenHost()).invoke(
            "list_documents"
        ).to_dict()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "host_unavailable")
        validate(payload, TOOL_CATALOG["list_documents"].output_schema)

    def test_invoke_publishes_one_activity_lifecycle_and_complete_timing(self) -> None:
        activity = OperationActivityStore(id_factory=lambda: "activity_invoke")
        observed = []
        activity.subscribe(observed.append)
        app = GlyphsMCPApplication(_FakeHost(), activity=activity)

        def slow_handler(_arguments):
            time.sleep(0.02)
            return ToolResponse.success(
                tool="get_server_info",
                effect="read",
                summary="Measured.",
                data={},
            )

        app._handlers["get_server_info"] = slow_handler
        payload = app.invoke("get_server_info").to_dict()

        self.assertEqual(observed[0].phase, "preparing")
        self.assertEqual(observed[-1].state, "success")
        self.assertGreaterEqual(payload["durationMs"], 15)

    def test_unknown_retired_endpoint_is_a_closed_failure(self) -> None:
        payload = GlyphsMCPApplication(_FakeHost()).invoke(
            "review_spacing", {}
        ).to_dict()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "unknown_tool")


if __name__ == "__main__":
    unittest.main()
