"""Application-service tests for the first Glyphs MCP 2.0 vertical slice."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

from jsonschema import validate


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.application import ReadOnlyApplication  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
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


class V2ApplicationTests(unittest.TestCase):
    def test_server_info_is_typed_and_declares_v2(self) -> None:
        response = ReadOnlyApplication(_FakeHost()).invoke("get_server_info")
        payload = response.to_dict()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["apiMajor"], 2)
        self.assertEqual(payload["data"]["apiVersion"], "2.0")
        self.assertEqual(payload["data"]["host"]["openDocumentCount"], 1)
        validate(payload, TOOL_CATALOG["get_server_info"].output_schema)

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
