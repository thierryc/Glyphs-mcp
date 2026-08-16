"""Glyphs 3.5/4 adapter tests without importing or launching Glyphs."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.adapters.glyphs import GlyphsHostAdapter  # noqa: E402


class _RecordingExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, callback):
        self.calls += 1
        return callback()


class _Font:
    def __init__(self, native_id, family_name, path=None) -> None:
        self.native_id = native_id
        self.familyName = family_name
        self.filepath = path
        self.masters = [object(), object()]
        self.instances = [object()]
        self.glyphs = [object(), object(), object()]
        self.upm = 1000
        self.versionMajor = 1
        self.versionMinor = 2
        self.formatVersion = 3
        self.appVersion = "3400"
        self.parent = None


class _Document:
    def __init__(self, font) -> None:
        self.font = font


class _Glyphs:
    versionString = "4.0"
    buildNumber = 3400


class V2GlyphsAdapterTests(unittest.TestCase):
    def test_snapshots_are_captured_through_the_main_thread_port(self) -> None:
        font = _Font(1, "Alpha", "/tmp/Alpha.glyphs")
        app = _Glyphs()
        app.fonts = [font]
        app.documents = []
        app.currentDocument = None
        app.font = font
        executor = _RecordingExecutor()
        adapter = GlyphsHostAdapter(
            app,
            executor=executor,
            native_identity=lambda value: ("native", value.native_id),
        )

        runtime = adapter.runtime_snapshot()
        documents = adapter.list_documents()

        self.assertEqual(executor.calls, 2)
        self.assertEqual(runtime.application, "Glyphs")
        self.assertEqual(runtime.open_document_count, 1)
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].family_name, "Alpha")
        self.assertTrue(documents[0].active)
        self.assertEqual(documents[0].legacy_index, 0)
        self.assertTrue(documents[0].has_file_path)
        self.assertIsNone(documents[0].has_unsaved_changes)

    def test_fresh_proxy_objects_keep_the_same_document_id(self) -> None:
        first_proxy = _Font(77, "Unsaved")
        second_proxy = _Font(77, "Unsaved", "/tmp/NowSaved.glyphs")
        app = _Glyphs()
        app.fonts = [first_proxy]
        app.documents = [_Document(first_proxy)]
        app.currentDocument = _Document(first_proxy)
        app.font = first_proxy
        adapter = GlyphsHostAdapter(
            app,
            executor=_RecordingExecutor(),
            native_identity=lambda value: ("native", value.native_id),
        )

        before = adapter.list_documents()[0]
        app.fonts = [second_proxy]
        app.documents = [_Document(second_proxy)]
        app.currentDocument = _Document(second_proxy)
        app.font = second_proxy
        after = adapter.list_documents()[0]

        self.assertEqual(before.document_id, after.document_id)
        self.assertIsNone(before.file_path)
        self.assertEqual(after.file_path, "/tmp/NowSaved.glyphs")

    def test_broken_fonts_proxy_falls_back_to_documents_and_active_font(self) -> None:
        class BrokenProxy:
            def __len__(self):
                raise RuntimeError("broken proxy")

            def __iter__(self):
                raise RuntimeError("broken proxy")

        font = _Font(9, "Fallback")
        app = _Glyphs()
        app.fonts = BrokenProxy()
        app.documents = [_Document(font)]
        app.currentDocument = _Document(font)
        app.font = font
        adapter = GlyphsHostAdapter(
            app,
            executor=_RecordingExecutor(),
            native_identity=lambda value: ("native", value.native_id),
        )

        documents = adapter.list_documents()

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].family_name, "Fallback")


if __name__ == "__main__":
    unittest.main()
