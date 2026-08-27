"""Application-service tests for the first Glyphs MCP 2.0 vertical slice."""

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

from glyphs_mcp_v2.application import ReadOnlyApplication  # noqa: E402
from glyphs_mcp_v2.activity import OperationActivityStore  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.contracts import ToolResponse  # noqa: E402
from glyphs_mcp_v2.ports import (  # noqa: E402
    FontSnapshot,
    HostAccessError,
    HostRuntimeSnapshot,
)


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
                master_count=2,
                instance_count=3,
                glyph_count=400,
                units_per_em=1000,
                version_major=1,
                version_minor=0,
                format_version=3,
                last_saved_app_version="3300",
            ),
        )

    def runtime_snapshot(self) -> HostRuntimeSnapshot:
        return HostRuntimeSnapshot(
            application="Glyphs",
            application_version="4.0",
            build_number="3400",
            python_version="3.12.3",
            open_document_count=1,
        )

    def list_documents(self):
        return self.documents


class _Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


class V2ApplicationTests(unittest.TestCase):
    def test_open_edit_tab_is_atomic_and_records_no_document_change(self) -> None:
        class UIHost(_FakeHost):
            def __init__(self) -> None:
                super().__init__()
                self.model = {
                    "font": {"familyName": "Alpha"},
                    "masters": [{"id": "m1", "name": "Regular"}],
                    "instances": [],
                    "glyphs": {
                        "A": {"name": "A", "id": "gA", "layers": []},
                        "B": {"name": "B", "id": "gB", "layers": []},
                    },
                    "kerning": {},
                    "features": [],
                    "classes": [],
                    "featurePrefixes": [],
                }
                self.opened = []

            def capture_model(self, _document_id):
                return copy.deepcopy(self.model)

            def open_edit_tab(self, document_id, glyph_names, *, master_id=None):
                self.opened.append((document_id, tuple(glyph_names), master_id))

        host = UIHost()
        app = ReadOnlyApplication(host)
        opened = app.invoke(
            "open_edit_tab",
            {
                "documentId": "doc_alpha",
                "glyphNames": ["A", "B"],
                "masterId": "m1",
            },
        ).to_dict()

        self.assertTrue(opened["ok"])
        self.assertEqual(opened["effect"], "ui")
        self.assertEqual(
            host.opened, [("doc_alpha", ("A", "B"), "m1")]
        )
        self.assertFalse(opened["data"]["documentChanged"])
        self.assertEqual(
            opened["data"]["beforeFingerprint"],
            opened["data"]["afterFingerprint"],
        )
        self.assertFalse(app.history.list_commits("doc_alpha")[-1].changed)
        validate(opened, TOOL_CATALOG["open_edit_tab"].output_schema)

        missing = app.invoke(
            "open_edit_tab",
            {"documentId": "doc_alpha", "glyphNames": ["A", "Missing"]},
        ).to_dict()
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error"]["code"], "target_not_found")
        self.assertEqual(len(host.opened), 1)

        duplicate = app.invoke(
            "open_edit_tab",
            {"documentId": "doc_alpha", "glyphNames": ["A", "A"]},
        ).to_dict()
        self.assertFalse(duplicate["ok"])
        self.assertEqual(duplicate["error"]["code"], "invalid_request")
        self.assertEqual(len(host.opened), 1)

    def test_kerning_entry_kind_filters_and_scopes_pagination_cursors(self) -> None:
        class ModelHost(_FakeHost):
            def capture_model(self, _document_id):
                return {
                    "glyphs": {
                        name: {"id": "g{}".format(name), "name": name}
                        for name in ("L", "quoteright", "A", "V")
                    },
                    "kerning": {
                        "ltr": {
                            "m1": {
                                "gA": {"gV": -80},
                                "gV": {"gA": -70},
                            }
                        },
                        "rtl": {},
                        "vertical": {},
                        "context": {"L * quoteright A": {"m1": -40}},
                    },
                }

        app = ReadOnlyApplication(ModelHost())
        pair_page = app.invoke(
            "list_kerning_pairs",
            {"documentId": "doc_alpha", "entryKind": "pair", "pageSize": 1},
        ).to_dict()
        context_page = app.invoke(
            "list_kerning_pairs",
            {"documentId": "doc_alpha", "entryKind": "context"},
        ).to_dict()

        self.assertTrue(pair_page["ok"])
        self.assertEqual(pair_page["data"]["pairs"][0]["entryKind"], "pair")
        self.assertEqual(
            context_page["data"]["pairs"][0]["entryKind"], "context"
        )
        crossed = app.invoke(
            "list_kerning_pairs",
            {
                "documentId": "doc_alpha",
                "entryKind": "context",
                "cursor": pair_page["page"]["nextCursor"],
            },
        ).to_dict()
        self.assertFalse(crossed["ok"])

    def test_invoke_publishes_one_event_driven_activity_lifecycle(self) -> None:
        activity = OperationActivityStore(id_factory=lambda: "activity_invoke")
        observed = []
        activity.subscribe(observed.append)
        app = ReadOnlyApplication(_FakeHost(), activity=activity)

        response = app.invoke("get_server_info")

        self.assertTrue(response.ok)
        self.assertEqual(observed[0].phase, "preparing")
        self.assertEqual(observed[-1].state, "success")
        self.assertEqual(activity.current(None).state, "success")

    def test_invoke_reports_the_complete_handler_wall_time(self) -> None:
        app = ReadOnlyApplication(_FakeHost())

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

        self.assertGreaterEqual(payload["durationMs"], 15)
        self.assertNotEqual(payload["startedAt"], payload["completedAt"])

    def test_server_info_is_typed_and_declares_v2(self) -> None:
        response = ReadOnlyApplication(_FakeHost()).invoke("get_server_info")
        payload = response.to_dict()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["apiMajor"], 2)
        self.assertEqual(payload["data"]["apiVersion"], "2.0")
        self.assertEqual(payload["data"]["canonicalModelSchemaVersion"], 6)
        self.assertIn("contextual_kerning", payload["data"]["capabilities"])
        self.assertEqual(payload["data"]["host"]["openDocumentCount"], 1)
        validate(payload, TOOL_CATALOG["get_server_info"].output_schema)

    def test_unexpected_invocation_exit_terminalizes_once_and_releases_lease(self) -> None:
        class TransportInterrupted(BaseException):
            pass

        activity = OperationActivityStore(id_factory=lambda: "activity_abort")
        observed = []
        activity.subscribe(observed.append)
        app = ReadOnlyApplication(_FakeHost(), activity=activity)
        app._handlers["get_server_info"] = lambda _arguments: (_ for _ in ()).throw(
            TransportInterrupted()
        )

        with self.assertRaises(TransportInterrupted):
            app.invoke("get_server_info")

        terminal = activity.current(None)
        self.assertEqual(terminal.state, "error")
        self.assertEqual(
            len([item for item in observed if item.state == "error"]), 1
        )
        self.assertIsNotNone(
            activity._lease_released_at[terminal.activity_id]
        )

    def test_synthetic_preparing_record_is_replaced_and_cleared_without_font_changes(self) -> None:
        clock = _Clock()
        ids = iter(("activity_stranded", "activity_command"))
        activity = OperationActivityStore(
            clock=clock, id_factory=lambda: next(ids)
        )
        stranded = activity.begin(
            document_id="doc_alpha",
            tool="execute_python",
            title="Execute Python",
        )
        activity.release(stranded)
        host = _FakeHost()
        before = host.documents[0]
        app = ReadOnlyApplication(host, activity=activity)

        response = app.invoke(
            "list_open_fonts", {"documentId": "doc_alpha"}
        )

        self.assertTrue(response.ok)
        current = activity.current("doc_alpha")
        self.assertEqual(current.activity_id, "activity_command")
        self.assertEqual(current.state, "success")
        activity.dismiss("doc_alpha")
        self.assertEqual(activity.current("doc_alpha").state, "idle")
        clock.value += 30.0
        activity.reconcile_orphans(grace_seconds=30.0)
        self.assertEqual(activity.current("doc_alpha").state, "idle")
        self.assertEqual(host.documents[0], before)
        self.assertFalse(host.documents[0].has_unsaved_changes)

    def test_list_open_fonts_uses_stable_document_ids_as_normative_targets(self) -> None:
        response = ReadOnlyApplication(_FakeHost()).invoke("list_open_fonts")
        payload = response.to_dict()
        document = payload["data"]["documents"][0]

        self.assertEqual(document["documentId"], "doc_alpha")
        self.assertEqual(document["legacyIndex"], 0)
        self.assertTrue(document["hasFilePath"])
        self.assertFalse(document["hasUnsavedChanges"])
        self.assertNotIn("saved", document)
        self.assertTrue(document["active"])
        validate(payload, TOOL_CATALOG["list_open_fonts"].output_schema)

    def test_host_failures_are_normalized_without_transport_exceptions(self) -> None:
        class BrokenHost(_FakeHost):
            def list_documents(self):
                raise HostAccessError("Glyphs is busy")

        response = ReadOnlyApplication(BrokenHost()).invoke("list_open_fonts")
        payload = response.to_dict()

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "host_unavailable")
        self.assertTrue(payload["error"]["recoverable"])
        validate(payload, TOOL_CATALOG["list_open_fonts"].output_schema)


if __name__ == "__main__":
    unittest.main()
