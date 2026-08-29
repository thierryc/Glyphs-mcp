"""Generic OpenType reads and detached compilation diagnostics."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.semantic import fingerprint_model  # noqa: E402


def _model() -> dict:
    return {
        "font": {"familyName": "OpenType Test", "upm": 1000},
        "masters": [],
        "instances": [],
        "glyphs": {},
        "kerning": {},
        "features": [
            {
                "id": "ss01",
                "name": "ss01",
                "tag": "ss01",
                "code": "sub [a b] by [a.ss01 b.ss01];",
                "automatic": False,
                "disabled": False,
            }
        ],
        "classes": [
            {
                "id": "Uppercase",
                "name": "Uppercase",
                "code": "A B C",
                "automatic": True,
                "disabled": False,
            }
        ],
        "featurePrefixes": [],
    }


class _Host:
    def __init__(self, diagnostics: dict | None = None) -> None:
        self.model = _model()
        self.diagnostics = diagnostics
        self.inspection_calls = 0

    def capture_model(self, _document_id: str) -> dict:
        return copy.deepcopy(self.model)

    def inspect_compilation_diagnostics(self, _document_id: str) -> dict:
        self.inspection_calls += 1
        return copy.deepcopy(
            self.diagnostics
            if self.diagnostics is not None
            else {
                "succeeded": True,
                "errorType": None,
                "errorMessage": None,
                "detached": True,
                "liveAttempted": False,
            }
        )


class V2OpenTypeToolTests(unittest.TestCase):
    def test_canonical_feature_and_class_fields_are_generic_reads(self) -> None:
        app = GlyphsMCPApplication(_Host())
        feature = app.invoke(
            "read_document",
            {
                "documentId": "doc_opentype",
                "selector": {"entity": "feature", "ids": ["ss01"]},
                "projection": {
                    "fields": ["id", "name", "tag", "code", "automatic", "disabled"]
                },
            },
        ).to_dict()
        opentype_class = app.invoke(
            "read_document",
            {
                "documentId": "doc_opentype",
                "selector": {"entity": "class", "ids": ["Uppercase"]},
                "projection": {"fields": ["id", "name", "code", "automatic"]},
            },
        ).to_dict()

        self.assertEqual(feature["data"]["items"][0]["values"]["tag"], "ss01")
        self.assertEqual(
            opentype_class["data"]["items"][0]["values"]["code"], "A B C"
        )

    def test_compilation_diagnostics_are_detached_evidence_not_an_effect(self) -> None:
        host = _Host()
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)
        response = app.invoke(
            "read_document",
            {
                "documentId": "doc_opentype",
                "selector": {"entity": "document", "ids": ["document"]},
                "projection": {"fields": ["compilation.diagnostics"]},
            },
        ).to_dict()

        self.assertTrue(response["ok"], response)
        item = response["data"]["items"][0]
        self.assertTrue(item["values"]["compilation.diagnostics"]["succeeded"])
        self.assertEqual(
            item["provenance"]["compilation.diagnostics"], "detached-native"
        )
        self.assertFalse(
            item["values"]["compilation.diagnostics"]["liveAttempted"]
        )
        self.assertEqual(host.inspection_calls, 1)
        self.assertEqual(fingerprint_model(host.model), before)

    def test_failed_detached_compilation_is_specific_complete_evidence(self) -> None:
        host = _Host(
            {
                "succeeded": False,
                "errorType": "FeatureError",
                "errorMessage": "invalid feature source",
                "detached": True,
                "liveAttempted": False,
            }
        )
        response = GlyphsMCPApplication(host).invoke(
            "read_document",
            {
                "documentId": "doc_opentype",
                "selector": {"entity": "document"},
                "projection": {"fields": ["compilation.diagnostics"]},
            },
        ).to_dict()

        item = response["data"]["items"][0]
        self.assertEqual(item["completeness"], "complete")
        self.assertFalse(item["values"]["compilation.diagnostics"]["succeeded"])
        self.assertEqual(
            item["values"]["compilation.diagnostics"]["errorType"], "FeatureError"
        )

    def test_live_compile_endpoint_is_removed_in_favor_of_permanent_python(self) -> None:
        self.assertNotIn("compile_opentype_features", TOOL_CATALOG)
        self.assertIn("execute_python", TOOL_CATALOG)


if __name__ == "__main__":
    unittest.main()
