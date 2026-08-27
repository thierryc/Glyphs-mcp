"""Typed OpenType inspection and compile-only workflow coverage."""

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
from glyphs_mcp_v2.semantic import fingerprint_model  # noqa: E402
from glyphs_mcp_v2.workflows import list_opentype_items  # noqa: E402


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
                "code": "sub [a b] by [a.ss01 b.ss01]; sub a' b by c;",
                "automatic": False,
                "disabled": False,
                "notes": "Name: Rounded alternates",
                "labels": [{"language": "dflt", "value": "Rounded"}],
            }
        ],
        "classes": [
            {
                "id": "Uppercase",
                "name": "Uppercase",
                "tag": "Uppercase",
                "code": "A B C",
                "automatic": True,
                "disabled": False,
                "notes": None,
                "labels": [],
            }
        ],
        "featurePrefixes": [],
    }


class _Host:
    def __init__(self) -> None:
        self.model = _model()
        self.compile_result = {
            "preflightSucceeded": True,
            "liveAttempted": True,
            "liveSucceeded": True,
            "errorType": None,
            "errorMessage": None,
        }
        self.force_dirty_calls = 0
        self.source_state = {
            "kind": "glyphs",
            "exists": True,
            "contentFingerprint": "sha256:source",
        }

    def capture_model(self, document_id):
        return copy.deepcopy(self.model)

    def compile_opentype_features(self, document_id):
        return dict(self.compile_result)

    def capture_source_file_state(self, document_id):
        return dict(self.source_state)

    def force_document_dirty(self, document_id):
        self.force_dirty_calls += 1


class V2OpenTypeToolTests(unittest.TestCase):
    def test_inspection_keeps_order_and_reports_unsupported_style_set_rules(self) -> None:
        items = list_opentype_items(_model())

        self.assertEqual([item["kind"] for item in items], ["feature", "class"])
        self.assertEqual(items[0]["order"], 0)
        self.assertTrue(items[0]["stylisticSet"])
        self.assertEqual(
            items[0]["substitutions"],
            [
                {"source": "a", "replacement": "a.ss01"},
                {"source": "b", "replacement": "b.ss01"},
            ],
        )
        self.assertEqual(items[0]["unsupportedRuleCount"], 1)
        self.assertTrue(items[0]["warnings"])

    def test_compile_succeeds_only_when_canonical_and_source_state_are_unchanged(self) -> None:
        host = _Host()
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)

        response = app.invoke(
            "compile_opentype_features",
            {
                "documentId": "doc_opentype",
                "expectedDocumentFingerprint": before,
            },
        ).to_dict()

        self.assertTrue(response["ok"])
        self.assertTrue(response["data"]["preflightSucceeded"])
        self.assertTrue(response["data"]["liveSucceeded"])
        self.assertEqual(response["data"]["observedAfterFingerprint"], before)
        self.assertEqual(response["data"]["observedChangeCount"], 0)
        self.assertFalse(response["data"]["sourceFileChanged"])
        self.assertFalse(response["data"]["fontSaved"])

    def test_detached_compile_failure_never_attempts_live_compile(self) -> None:
        host = _Host()
        host.compile_result = {
            "preflightSucceeded": False,
            "liveAttempted": False,
            "liveSucceeded": False,
            "errorType": "FeatureError",
            "errorMessage": "invalid feature source",
        }
        app = GlyphsMCPApplication(host)

        response = app.invoke(
            "compile_opentype_features",
            {
                "documentId": "doc_opentype",
                "expectedDocumentFingerprint": fingerprint_model(host.model),
            },
        ).to_dict()

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "opentype_preflight_failed")
        self.assertFalse(response["data"]["liveAttempted"])

    def test_compile_detects_unexpected_canonical_change_and_forces_dirty(self) -> None:
        host = _Host()

        def changed_compile(document_id):
            host.model["font"]["familyName"] = "Unexpected"
            return dict(host.compile_result)

        host.compile_opentype_features = changed_compile
        app = GlyphsMCPApplication(host)
        before = fingerprint_model(host.model)

        response = app.invoke(
            "compile_opentype_features",
            {
                "documentId": "doc_opentype",
                "expectedDocumentFingerprint": before,
            },
        ).to_dict()

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "opentype_state_changed")
        self.assertTrue(response["data"]["stateMayHaveChanged"])
        self.assertEqual(response["data"]["observedChangeCount"], 1)
        self.assertEqual(host.force_dirty_calls, 1)


if __name__ == "__main__":
    unittest.main()
