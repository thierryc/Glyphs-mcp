"""Disposable-host guards for the generic Glyphs 4 live qualification gates."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.live_gates import (  # noqa: E402
    _assert_unique_unicode_assignments,
    verify_copy_and_make_copy,
    verify_generic_change_lifecycle,
    verify_generic_kerning_lifecycle,
    verify_open_document_view,
    verify_staged_python_preview_lifecycle,
)
from glyphs_mcp_v2.semantic import fingerprint_model  # noqa: E402


class _Document:
    def __init__(self) -> None:
        self.isDocumentEdited = True


class _Font:
    def __init__(self, family_name: str = "Glyphs MCP V2 Disposable Test") -> None:
        self.familyName = family_name
        self.filepath = "/disposable/source.glyphs"
        self.parent = _Document()
        self.selectedFontMaster = SimpleNamespace(id="m0")

    def copy(self):
        return _Font(self.familyName)

    def save(self, path, formatVersion=3, makeCopy=False):
        destination = Path(path)
        if destination.suffix == ".glyphspackage":
            destination.mkdir()
            destination = destination / "fontinfo.plist"
        destination.write_text("stable disposable archive", encoding="utf-8")


def _model() -> dict:
    return {
        "font": {
            "familyName": "Glyphs MCP V2 Disposable Gate",
            "upm": 1000,
            "note": None,
        },
        "masters": [
            {
                "id": "m0",
                "name": "Regular",
                "italicAngle": 0,
                "axes": [{"tag": "wght", "internal": 100}],
            }
        ],
        "instances": [],
        "glyphs": {
            "A": {
                "id": "glyph_A",
                "name": "A",
                "unicode": "0041",
                "export": True,
                "layers": [
                    {
                        "id": "m0",
                        "masterId": "m0",
                        "name": "Regular",
                        "roles": ["master"],
                        "isMasterLayer": True,
                        "isSpecialLayer": False,
                        "width": 600,
                        "shapes": [],
                        "anchors": [],
                    }
                ],
            }
        },
        "kerning": {
            "ltr": {"m0": {"glyph_A": {"glyph_A": -20}}},
            "rtl": {},
            "vertical": {},
            "context": {},
        },
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


class _Host:
    def __init__(self) -> None:
        self.model = _model()
        self.apply_calls = 0
        self.restore_calls = 0
        self.open_calls: list[tuple[str, tuple[str, ...], str | None]] = []

    def document_id_for_font(self, _font) -> str:
        return "doc_live_gate"

    def capture_model(self, document_id: str) -> dict:
        if document_id != "doc_live_gate":
            raise ValueError("wrong document")
        return copy.deepcopy(self.model)

    def simulate_change_set(self, _document_id: str, change_set):
        return change_set.apply(self.model)

    def simulate_reconciliation(
        self, _document_id, _change_set, required_after_model, _before_model
    ):
        return {
            "afterModel": copy.deepcopy(required_after_model),
            "replayReplacements": [],
        }

    def apply_change_set(self, _document_id: str, change_set) -> None:
        self.apply_calls += 1
        self.model = change_set.apply(self.model)

    def restore_model(self, _document_id: str, model: dict) -> None:
        self.restore_calls += 1
        self.model = copy.deepcopy(model)

    def open_edit_tab(self, document_id, glyph_names, *, master_id=None):
        self.open_calls.append((document_id, tuple(glyph_names), master_id))
        return {"openedTab": True, "glyphNames": list(glyph_names)}


class _PythonHost(_Host):
    def preview_python(self, _request, before_model):
        after = copy.deepcopy(before_model)
        after["font"]["note"] = "Glyphs MCP staged qualification"
        return {
            "afterModel": after,
            "stdout": "",
            "stderr": "",
            "scopeViolations": [],
        }

    def run_live_python(self, _request):
        raise AssertionError("staged gate attempted live Python")

    def create_recovery_copy(self, _document_id, execution_id):
        return "/private/recovery/{}.glyphs".format(execution_id)


def _copy_host(source: dict, *, observed_clone: dict | None = None):
    observed_clone = source if observed_clone is None else observed_clone
    return SimpleNamespace(
        document_id_for_font=mock.Mock(return_value="doc_copy_gate"),
        capture_snapshot=mock.Mock(return_value=source),
        _instance_ids_for_font=mock.Mock(return_value=[]),
        _capture_detached_model=mock.Mock(return_value=observed_clone),
        _reconcile_detached_clone=mock.Mock(return_value=(source, object())),
        list_documents=mock.Mock(
            return_value=[
                SimpleNamespace(
                    document_id="doc_copy_gate", has_unsaved_changes=True
                )
            ]
        ),
    )


class V2LiveGateGuardTests(unittest.TestCase):
    def test_open_document_view_is_a_non_document_ui_transition(self) -> None:
        host = _Host()
        result = verify_open_document_view(
            _Font(), ["A"], application=GlyphsMCPApplication(host), host=host
        )

        self.assertEqual(host.open_calls, [("doc_live_gate", ("A",), "m0")])
        self.assertTrue(result["openedView"])
        self.assertTrue(result["documentUnchanged"])

    def test_ui_gate_refuses_non_disposable_fonts_before_effect(self) -> None:
        host = _Host()
        with self.assertRaises(ValueError):
            verify_open_document_view(
                _Font("Production Family"),
                ["A"],
                application=GlyphsMCPApplication(host),
                host=host,
            )
        self.assertEqual(host.open_calls, [])

    def test_duplicate_unicode_is_refused_before_mutation(self) -> None:
        model = _model()
        model["glyphs"]["e"] = copy.deepcopy(model["glyphs"]["A"])
        model["glyphs"]["e"]["name"] = "e"
        with self.assertRaisesRegex(ValueError, "U\\+0041.*A.*e"):
            _assert_unique_unicode_assignments(model, phase="baseline")

    def test_unencoded_and_distinct_unicode_are_allowed(self) -> None:
        model = _model()
        model["glyphs"]["unencoded"] = {
            "id": "glyph_unencoded",
            "name": "unencoded",
            "unicode": None,
            "layers": [],
        }
        _assert_unique_unicode_assignments(model, phase="baseline")

    def test_copy_gate_preserves_path_dirty_state_and_canonical_snapshot(self) -> None:
        source = {"font": {"familyName": "Glyphs MCP V2 Disposable Test"}}
        with tempfile.TemporaryDirectory() as root:
            font = _Font()
            result = verify_copy_and_make_copy(
                font,
                str(Path(root) / "copy.glyphs"),
                application=object(),
                host=_copy_host(source),
            )
        self.assertTrue(result["workingPathUnchanged"])
        self.assertTrue(result["dirtyStateUnchanged"])
        self.assertEqual(result["copyFingerprint"], fingerprint_model(source))

    def test_copy_gate_uses_the_shared_detached_projection_boundary(self) -> None:
        source = {"font": {"familyName": "Glyphs MCP V2 Disposable Test"}}
        observed = copy.deepcopy(source)
        observed["font"]["note"] = "clone artifact"
        host = _copy_host(source, observed_clone=observed)
        host._reconcile_detached_clone.return_value = (
            source,
            SimpleNamespace(artifacts=SimpleNamespace(changes=[])),
        )
        with tempfile.TemporaryDirectory() as root:
            verify_copy_and_make_copy(
                _Font(),
                str(Path(root) / "copy.glyphs"),
                application=object(),
                host=host,
            )
        host._capture_detached_model.assert_called_once()
        host._reconcile_detached_clone.assert_called_once()

    def test_generic_change_gate_qualifies_structure_and_restores_baseline(self) -> None:
        host = _Host()
        before = copy.deepcopy(host.model)
        result = verify_generic_change_lifecycle(
            _Font(), application=GlyphsMCPApplication(host), host=host
        )

        self.assertEqual(host.model, before)
        self.assertEqual(result["successfulTransactionCount"], 8)
        self.assertEqual(result["refusalCount"], 1)
        self.assertTrue(result["exactBaselineRestored"])
        self.assertTrue(result["auditReceiptsPresent"])
        self.assertTrue(result["historyEntriesPresent"])

    def test_generic_gate_cleanup_restores_baseline_after_a_later_failure(self) -> None:
        host = _Host()
        app = GlyphsMCPApplication(host)
        before = copy.deepcopy(host.model)
        original = app.invoke
        calls = 0

        def fail_later(tool, arguments=None):
            nonlocal calls
            calls += 1
            if calls == 5:
                raise RuntimeError("injected gate failure")
            return original(tool, arguments)

        app.invoke = fail_later
        with self.assertRaises(RuntimeError):
            verify_generic_change_lifecycle(_Font(), application=app, host=host)
        self.assertEqual(host.model, before)

    def test_generic_kerning_gate_preserves_pair_domains(self) -> None:
        host = _Host()
        before = copy.deepcopy(host.model)
        result = verify_generic_kerning_lifecycle(
            _Font(), application=GlyphsMCPApplication(host), host=host
        )
        self.assertEqual(host.model, before)
        self.assertEqual(result["successfulTransactionCount"], 2)
        self.assertEqual(
            result["qualifiedDomains"],
            ["context_storage", "pair_domain_preservation", "atomic_refusal"],
        )

    def test_staged_python_gate_applies_through_generic_change_and_reverts(self) -> None:
        host = _PythonHost()
        before = copy.deepcopy(host.model)
        result = verify_staged_python_preview_lifecycle(
            _Font(), application=GlyphsMCPApplication(host), host=host
        )
        self.assertEqual(host.model, before)
        self.assertEqual(result["previewCount"], 1)
        self.assertEqual(result["successfulTransactionCount"], 2)
        self.assertTrue(result["exactBaselineRestored"])

    def test_generic_and_python_gates_refuse_non_disposable_fonts(self) -> None:
        for gate, host in (
            (verify_generic_change_lifecycle, _Host()),
            (verify_generic_kerning_lifecycle, _Host()),
            (verify_staged_python_preview_lifecycle, _PythonHost()),
        ):
            with self.subTest(gate=gate.__name__), self.assertRaises(ValueError):
                gate(
                    _Font("Production Family"),
                    application=GlyphsMCPApplication(host),
                    host=host,
                )
            self.assertEqual(host.apply_calls, 0)


if __name__ == "__main__":
    unittest.main()
