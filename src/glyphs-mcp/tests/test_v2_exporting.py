"""Destination-bound staged publication tests for Glyphs MCP 2.0."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.exporting import (  # noqa: E402
    ExportPublicationError,
    inspect_destination,
    publish_staged_directory,
)


class V2ExportPublicationTests(unittest.TestCase):
    @staticmethod
    def _producer(staged: Path):
        staged.mkdir()
        (staged / "Family.designspace").write_text("new", encoding="utf-8")
        return {"designspaceFiles": ["Family.designspace"]}

    def test_missing_destination_is_staged_and_verified(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "source"
            result = publish_staged_directory(
                destination=str(destination),
                expected_state=inspect_destination(str(destination)),
                producer=self._producer,
            )
            self.assertEqual((destination / "Family.designspace").read_text(), "new")
            self.assertTrue(result["atomicPublication"])
            self.assertEqual(result["publishedFingerprint"], inspect_destination(str(destination))["fingerprint"])

    def test_stale_destination_is_refused_before_production(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "source"
            reviewed = inspect_destination(str(destination))
            destination.mkdir()
            (destination / "user.txt").write_text("later edit", encoding="utf-8")
            called = []
            with self.assertRaises(ExportPublicationError):
                publish_staged_directory(
                    destination=str(destination),
                    expected_state=reviewed,
                    producer=lambda staged: called.append(staged) or {},
                )
            self.assertEqual(called, [])
            self.assertEqual((destination / "user.txt").read_text(), "later edit")

    @unittest.skipUnless(sys.platform == "darwin", "macOS atomic directory swap")
    def test_matching_nonempty_destination_is_atomically_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "source"
            destination.mkdir()
            (destination / "old.txt").write_text("old", encoding="utf-8")
            reviewed = inspect_destination(str(destination))
            result = publish_staged_directory(
                destination=str(destination),
                expected_state=reviewed,
                producer=self._producer,
            )
            self.assertFalse((destination / "old.txt").exists())
            self.assertEqual((destination / "Family.designspace").read_text(), "new")
            self.assertEqual(result["replacedDestinationFingerprint"], reviewed["fingerprint"])


if __name__ == "__main__":
    unittest.main()
