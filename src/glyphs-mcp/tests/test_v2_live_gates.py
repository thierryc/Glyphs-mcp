"""Static disposable-host guards for the Glyphs 4 live gate."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.live_gates import verify_copy_and_make_copy  # noqa: E402


class _Document:
    def __init__(self):
        self.isDocumentEdited = True


class _Font:
    def __init__(self, family_name="Glyphs MCP V2 Disposable Test"):
        self.familyName = family_name
        self.filepath = "/disposable/source.glyphs"
        self.parent = _Document()
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

    def copy(self):
        return _Font(self.familyName)

    def save(self, path, formatVersion=3, makeCopy=False):
        Path(path).write_text("stable disposable archive", encoding="utf-8")


class V2LiveGateGuardTests(unittest.TestCase):
    def test_gate_refuses_non_disposable_font(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                verify_copy_and_make_copy(_Font("Production Family"), str(Path(root) / "copy.glyphs"))

    def test_gate_preserves_path_and_dirty_state(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            font = _Font()
            result = verify_copy_and_make_copy(font, str(Path(root) / "copy.glyphs"))
            self.assertTrue(result["workingPathUnchanged"])
            self.assertTrue(result["dirtyStateUnchanged"])
            self.assertEqual(font.filepath, "/disposable/source.glyphs")
            self.assertTrue(font.parent.isDocumentEdited)


if __name__ == "__main__":
    unittest.main()
