"""Static disposable-host guard tests for the manual Glyphs 3.5/4 gate."""

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
    def __init__(
        self,
        family_name="Glyphs MCP V2 Disposable Test",
        *,
        archive_payload="stable disposable archive",
        clone_archive_payload=None,
    ):
        self.familyName = family_name
        self._archive_payload = archive_payload
        self._clone_archive_payload = clone_archive_payload or archive_payload
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
        return _Font(
            self.familyName,
            archive_payload=self._clone_archive_payload,
            clone_archive_payload=self._clone_archive_payload,
        )

    def save(self, path, formatVersion=3, makeCopy=False):
        Path(path).write_text(self._archive_payload, encoding="utf-8")


class _NondeterministicCopyFont(_Font):
    def __init__(self):
        super().__init__(archive_payload="live presentation archive")
        self._copy_count = 0

    def copy(self):
        self._copy_count += 1
        return _Font(archive_payload="detached archive {}".format(self._copy_count))


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

    def test_gate_compares_two_detached_archives_not_live_presentation_state(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            font = _Font(
                archive_payload="live archive with transient presentation state",
                clone_archive_payload="detached canonical archive",
            )
            result = verify_copy_and_make_copy(font, str(Path(root) / "copy.glyphs"))
            self.assertTrue(result["serializedCloneDeterministic"])
            self.assertEqual(result["archiveComparisonScope"], "detached_clone")

    def test_gate_rejects_nondeterministic_detached_archives(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(AssertionError, "deterministic detached archives"):
                verify_copy_and_make_copy(
                    _NondeterministicCopyFont(),
                    str(Path(root) / "copy.glyphs"),
                )


if __name__ == "__main__":
    unittest.main()
