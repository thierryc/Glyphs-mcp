"""Native-adapter recovery invariants exercised with disposable fakes."""

from __future__ import annotations

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
