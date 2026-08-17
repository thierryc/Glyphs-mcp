"""Native-adapter recovery invariants exercised with disposable fakes."""

from __future__ import annotations

import copy
import stat
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

from glyphs_mcp_v2.adapters.document import (  # noqa: E402
    GlyphsDocumentHost,
    native_font_to_model,
)
from glyphs_mcp_v2.adapters import document as document_adapter  # noqa: E402
from glyphs_mcp_v2.semantic import diff_models  # noqa: E402


class _Immediate:
    def run(self, callback):
        return callback()


class _Font:
    def __init__(self) -> None:
        self.familyName = "Recovery Test"
        self.filepath = "/fonts/original.glyphs"
        self.dirty = True
        self.saved = []

    def save(self, path, formatVersion=3, makeCopy=False):
        self.saved.append((path, formatVersion, makeCopy))
        Path(path).write_text("disposable recovery", encoding="utf-8")

    def copy(self):
        clone = _Font()
        clone.filepath = self.filepath
        clone.dirty = self.dirty
        return clone


class _NativeSelector:
    def __init__(self, value, owner):
        self.value = value
        self.owner = owner

    def __call__(self):
        return self.value

    def __str__(self):
        return "<native-selector id of {}>".format(self.owner)


class _Instance:
    def __init__(self, native_id, owner):
        self.id = _NativeSelector(native_id, owner)
        self.name = "Regular"
        self.type = 0
        self.active = True
        self.axes = [400]
        self.externalAxes = []


class _InstanceFont(_Font):
    def __init__(self, native_id, owner):
        super().__init__()
        self.axes = []
        self.masters = []
        self.instances = [_Instance(native_id, owner)]
        self.glyphs = []
        self.kerning = {}
        self.features = []
        self.classes = []
        self.featurePrefixes = []


class _ArchiveInstanceFont(_InstanceFont):
    def __init__(self, native_id, owner, *, unsupported_native_value="same"):
        super().__init__(native_id, owner)
        self.unsupported_native_value = unsupported_native_value

    def save(self, path, formatVersion=3, makeCopy=False):
        instance_id = self.instances[0].id()
        Path(path).write_text(
            "instances = (\n{id = \"%s\";}\n);\nunsupportedNativeValue = %s;\n"
            % (instance_id, self.unsupported_native_value),
            encoding="utf-8",
        )


class _Glyphs4SaveFont(_Font):
    def __init__(self, *, native_failure=False):
        super().__init__()
        self.formatVersion = 4
        self.tempData = {"filePath": "original-temp-path"}
        self.native_failure = native_failure
        self.native_calls = []

    def save(self, path, formatVersion=None, makeCopy=False):
        # Reproduce Glyphs 4.0.1: its Python wrapper sets tempData before
        # calling the removed saveToURL_type_format_error_ selector.
        self.tempData["filePath"] = path
        raise AttributeError("saveToURL_type_format_error_")

    def saveToURL_type_format_context_error_(
        self, url, type_id, format_version, context, error
    ):
        self.native_calls.append((url, type_id, format_version, context, error))
        if self.native_failure:
            raise RuntimeError("native save failed")
        Path(url).write_text("glyphs 4 recovery", encoding="utf-8")
        return True


class _App:
    def __init__(self, font) -> None:
        self.font = font
        self.fonts = [font]
        self.documents = []
        self.opened = []

    def open(self, path, showInterface=True):
        self.opened.append((path, showInterface))


class _EditableDocument:
    def __init__(self, *, edited=False, stale_unsaved_signal=False):
        self._preexisting_edits = 1 if edited else 0
        self._mcp_edits = 0
        self._stale_unsaved_signal = stale_unsaved_signal
        self.isDocumentEdited = edited
        self.hasUnautosavedChanges = edited and not stale_unsaved_signal
        self.change_counts = []

    def updateChangeCount_(self, change):
        self.change_counts.append(change)
        if change == 0:
            self._mcp_edits += 1
        elif change == 1:
            self._mcp_edits = max(0, self._mcp_edits - 1)
        elif change == 2:
            self._mcp_edits = 0
            self._preexisting_edits = 0
        self.isDocumentEdited = bool(self._preexisting_edits or self._mcp_edits)
        self.hasUnautosavedChanges = (
            False
            if self._stale_unsaved_signal
            else bool(self._preexisting_edits or self._mcp_edits)
        )


class _TransactionalFont:
    def __init__(self, *, edited=False, stale_unsaved_signal=False):
        self.familyName = "Transaction Test"
        self.filepath = "/fonts/transaction.glyphs"
        self.parent = _EditableDocument(
            edited=edited, stale_unsaved_signal=stale_unsaved_signal
        )
        self.upm = 1000
        self.versionMajor = 1
        self.versionMinor = 0
        self.note = None
        self.grid = 1
        self.gridSubDivision = 1
        self.axes = []
        self.masters = []
        self.instances = []
        self.glyphs = []
        self.kerning = {}
        self.features = []
        self.classes = []
        self.featurePrefixes = []


class _RecoveryHost(GlyphsDocumentHost):
    def __init__(self, app, root):
        super().__init__(app, executor=_Immediate())
        self._test_recovery_root = Path(root)

    def _recovery_root(self):
        return self._test_recovery_root


class V2DocumentAdapterTests(unittest.TestCase):
    def test_clone_generated_instance_ids_do_not_change_the_canonical_model(self) -> None:
        source = native_font_to_model(_InstanceFont("source-uuid", "source-pointer"))
        clone = native_font_to_model(_InstanceFont("clone-uuid", "clone-pointer"))

        self.assertEqual(source, clone)
        self.assertEqual(source["instances"][0]["id"], "instance_0")

    def test_serialized_fingerprint_normalizes_clone_generated_instance_ids(self) -> None:
        source = _ArchiveInstanceFont(
            "11111111-1111-4111-8111-111111111111", "source-pointer"
        )
        clone = _ArchiveInstanceFont(
            "22222222-2222-4222-8222-222222222222", "clone-pointer"
        )

        self.assertEqual(
            document_adapter._serialized_font_fingerprint(source),
            document_adapter._serialized_font_fingerprint(clone),
        )

    def test_serialized_fingerprint_keeps_other_native_fields_significant(self) -> None:
        source = _ArchiveInstanceFont(
            "11111111-1111-4111-8111-111111111111",
            "source-pointer",
            unsupported_native_value="before",
        )
        clone = _ArchiveInstanceFont(
            "22222222-2222-4222-8222-222222222222",
            "clone-pointer",
            unsupported_native_value="after",
        )

        self.assertNotEqual(
            document_adapter._serialized_font_fingerprint(source),
            document_adapter._serialized_font_fingerprint(clone),
        )

    def test_verified_transaction_marks_clean_document_dirty_and_inverse_clears_it(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        after = copy.deepcopy(before)
        after["font"]["note"] = "reviewed edit"
        change_set = diff_models(before, after)

        host.apply_change_set(document_id, change_set)

        self.assertTrue(font.parent.isDocumentEdited)
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)

        host.apply_change_set(document_id, change_set.inverse())

        self.assertFalse(font.parent.isDocumentEdited)
        self.assertFalse(host.list_documents()[0].has_unsaved_changes)
        self.assertEqual(font.parent.change_counts, [0, 1])
        self.assertNotIn(2, font.parent.change_counts)

    def test_verified_transaction_overrides_stale_native_unsaved_signal(self) -> None:
        font = _TransactionalFont(stale_unsaved_signal=True)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        after = copy.deepcopy(before)
        after["font"]["note"] = "reviewed edit"
        change_set = diff_models(before, after)

        host.apply_change_set(document_id, change_set)

        self.assertFalse(font.parent.hasUnautosavedChanges)
        self.assertTrue(host.list_documents()[0].has_unsaved_changes)

        host.apply_change_set(document_id, change_set.inverse())

        self.assertFalse(host.list_documents()[0].has_unsaved_changes)

    def test_inverse_preserves_dirty_state_that_predated_transaction(self) -> None:
        font = _TransactionalFont(edited=True)
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        after = copy.deepcopy(before)
        after["font"]["note"] = "reviewed edit"
        change_set = diff_models(before, after)

        host.apply_change_set(document_id, change_set)
        host.apply_change_set(document_id, change_set.inverse())

        self.assertTrue(font.parent.isDocumentEdited)
        self.assertNotIn(2, font.parent.change_counts)

    def test_failed_transaction_restoration_balances_dirty_state_after_divergence(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        after = copy.deepcopy(before)
        after["font"]["note"] = "reviewed edit"
        change_set = diff_models(before, after)

        host.apply_change_set(document_id, change_set)
        font.note = "divergent readback"
        host.restore_model(document_id, before)

        self.assertIsNone(font.note)
        self.assertFalse(font.parent.isDocumentEdited)
        self.assertEqual(font.parent.change_counts, [0, 1])

    def test_failed_rollback_restoration_reinstates_dirty_contribution(self) -> None:
        font = _TransactionalFont()
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.list_documents()[0].document_id
        before = host.capture_model(document_id)
        after = copy.deepcopy(before)
        after["font"]["note"] = "reviewed edit"
        change_set = diff_models(before, after)

        host.apply_change_set(document_id, change_set)
        host.apply_change_set(document_id, change_set.inverse())
        host.restore_model(document_id, after)

        self.assertEqual(font.note, "reviewed edit")
        self.assertTrue(font.parent.isDocumentEdited)
        self.assertEqual(font.parent.change_counts, [0, 1, 0])

        host.apply_change_set(document_id, change_set.inverse())
        self.assertFalse(font.parent.isDocumentEdited)
        self.assertEqual(font.parent.change_counts, [0, 1, 0, 1])

    def test_glyphs4_make_copy_fallback_restores_temp_data_and_native_format(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "checkpoint.glyphs"
            font = _Glyphs4SaveFont()
            foundation = SimpleNamespace(
                NSURL=SimpleNamespace(fileURLWithPath_=lambda value: value)
            )
            with mock.patch.dict(sys.modules, {"Foundation": foundation}):
                document_adapter._save_font_copy(font, destination)

            self.assertTrue(destination.is_file())
            self.assertEqual(font.tempData["filePath"], "original-temp-path")
            self.assertEqual(
                font.native_calls,
                [(str(destination), 1, 4, None, None)],
            )

    def test_glyphs4_make_copy_fallback_restores_temp_data_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "checkpoint.glyphs"
            font = _Glyphs4SaveFont(native_failure=True)
            foundation = SimpleNamespace(
                NSURL=SimpleNamespace(fileURLWithPath_=lambda value: value)
            )
            with mock.patch.dict(sys.modules, {"Foundation": foundation}):
                with self.assertRaises(RuntimeError):
                    document_adapter._save_font_copy(font, destination)

            self.assertEqual(font.tempData["filePath"], "original-temp-path")

    def test_recovery_copy_is_private_bounded_and_does_not_change_live_path(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            font = _Font()
            app = _App(font)
            host = _RecoveryHost(app, Path(root) / "private")
            document_id = host.list_documents()[0].document_id
            original_path, original_dirty = font.filepath, font.dirty
            latest = None
            for index in range(12):
                latest = host.create_recovery_copy(document_id, "review_{:02d}".format(index))

            copies = list((Path(root) / "private").glob("*.glyphs"))
            self.assertEqual(len(copies), 10)
            self.assertTrue(all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in copies))
            self.assertTrue(all(call[2] is True for call in font.saved))
            self.assertEqual(font.filepath, original_path)
            self.assertEqual(font.dirty, original_dirty)

            host.open_recovery_copy(str(latest))
            self.assertEqual(len(app.opened), 1)
            self.assertEqual(font.filepath, original_path)
            self.assertEqual(font.dirty, original_dirty)


if __name__ == "__main__":
    unittest.main()
