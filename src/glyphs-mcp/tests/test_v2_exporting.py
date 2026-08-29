"""Destination-bound staged publication tests for Glyphs MCP 2.0."""

from __future__ import annotations

import sys
import os
import tempfile
import unittest
from unittest import mock
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
import glyphs_mcp_v2.exporting as exporting_module  # noqa: E402


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

    def test_post_publication_inspection_error_restores_missing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "source"
            reviewed = inspect_destination(str(destination))
            resolved_destination = exporting_module.resolve_destination(str(destination))
            real_inspect = exporting_module._inspect_for_publication

            def fail_for_published_target(value):
                path = Path(value)
                if path == resolved_destination and (path / "Family.designspace").is_file():
                    raise ExportPublicationError("injected post-publication read failure")
                return real_inspect(value)

            with mock.patch.object(
                exporting_module,
                "_inspect_for_publication",
                side_effect=fail_for_published_target,
            ):
                with self.assertRaisesRegex(
                    ExportPublicationError, "reviewed destination was restored"
                ):
                    publish_staged_directory(
                        destination=str(destination),
                        expected_state=reviewed,
                        producer=self._producer,
                    )
            self.assertFalse(destination.exists())

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

    @unittest.skipUnless(sys.platform == "darwin", "macOS exclusive directory rename")
    def test_missing_destination_race_never_clobbers_late_directory(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "source"
            reviewed = inspect_destination(str(destination))
            resolved_destination = exporting_module.resolve_destination(str(destination))
            real_inspect = exporting_module._inspect_for_publication
            target_inspections = 0

            def inject_after_final_fence(value):
                nonlocal target_inspections
                path = Path(value)
                observed = real_inspect(value)
                if path == resolved_destination:
                    target_inspections += 1
                    if target_inspections == 2:
                        path.mkdir()
                        (path / "late.txt").write_text("user data", encoding="utf-8")
                return observed

            with mock.patch.object(
                exporting_module,
                "_inspect_for_publication",
                side_effect=inject_after_final_fence,
            ):
                with self.assertRaisesRegex(
                    ExportPublicationError,
                    "destination appeared during atomic publication",
                ):
                    publish_staged_directory(
                        destination=str(destination),
                        expected_state=reviewed,
                        producer=self._producer,
                    )

            self.assertEqual(
                (destination / "late.txt").read_text(encoding="utf-8"),
                "user data",
            )
            self.assertFalse((destination / "Family.designspace").exists())

    @unittest.skipUnless(sys.platform == "darwin", "macOS exclusive directory rename")
    def test_missing_destination_race_reports_late_symlink_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            destination = base / "source"
            outside = base / "outside"
            outside.mkdir()
            reviewed = inspect_destination(str(destination))
            resolved_destination = exporting_module.resolve_destination(str(destination))
            real_inspect = exporting_module._inspect_for_publication
            target_inspections = 0

            def inject_after_final_fence(value):
                nonlocal target_inspections
                path = Path(value)
                observed = real_inspect(value)
                if path == resolved_destination:
                    target_inspections += 1
                    if target_inspections == 2:
                        path.symlink_to(outside, target_is_directory=True)
                return observed

            with mock.patch.object(
                exporting_module,
                "_inspect_for_publication",
                side_effect=inject_after_final_fence,
            ):
                with self.assertRaises(ExportPublicationError):
                    publish_staged_directory(
                        destination=str(destination),
                        expected_state=reviewed,
                        producer=self._producer,
                    )

            self.assertTrue(destination.is_symlink())
            self.assertEqual(list(outside.iterdir()), [])

    def test_symlink_ancestors_and_tree_entries_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            real = base / "real"
            real.mkdir()
            alias = base / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                inspect_destination(str(alias / "bundle"))

            destination = base / "bundle"
            destination.mkdir()
            (destination / "escape").symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                inspect_destination(str(destination))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX named pipes")
    def test_special_tree_objects_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "bundle"
            destination.mkdir()
            os.mkfifo(destination / "pipe")
            with self.assertRaisesRegex(ValueError, "unsupported filesystem object"):
                inspect_destination(str(destination))

    def test_missing_destination_parent_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "missing" / "bundle"
            with self.assertRaisesRegex(ValueError, "parent directory"):
                inspect_destination(str(destination))

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

    @unittest.skipUnless(sys.platform == "darwin", "macOS atomic directory swap")
    def test_post_swap_inspection_error_restores_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "source"
            destination.mkdir()
            (destination / "old.txt").write_text("old", encoding="utf-8")
            reviewed = inspect_destination(str(destination))
            resolved_destination = exporting_module.resolve_destination(str(destination))
            real_inspect = exporting_module._inspect_for_publication

            def fail_for_published_target(value):
                path = Path(value)
                if path == resolved_destination and (path / "Family.designspace").is_file():
                    raise ExportPublicationError("injected post-swap read failure")
                return real_inspect(value)

            with mock.patch.object(
                exporting_module,
                "_inspect_for_publication",
                side_effect=fail_for_published_target,
            ):
                with self.assertRaisesRegex(
                    ExportPublicationError, "reviewed destination was restored"
                ):
                    publish_staged_directory(
                        destination=str(destination),
                        expected_state=reviewed,
                        producer=self._producer,
                    )
            self.assertEqual((destination / "old.txt").read_text(), "old")
            self.assertFalse((destination / "Family.designspace").exists())

    @unittest.skipUnless(sys.platform == "darwin", "macOS atomic directory swap")
    def test_failed_post_swap_restoration_preserves_displaced_tree(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            destination = base / "source"
            destination.mkdir()
            (destination / "old.txt").write_text("old", encoding="utf-8")
            reviewed = inspect_destination(str(destination))
            resolved_destination = exporting_module.resolve_destination(str(destination))
            real_inspect = exporting_module._inspect_for_publication
            real_swap = exporting_module._atomic_swap
            swap_count = 0

            def fail_for_published_target(value):
                path = Path(value)
                if path == resolved_destination and (path / "Family.designspace").is_file():
                    raise ExportPublicationError("injected post-swap read failure")
                return real_inspect(value)

            def fail_restoration(left, right):
                nonlocal swap_count
                swap_count += 1
                if swap_count == 2:
                    raise ExportPublicationError("injected restoration failure")
                return real_swap(left, right)

            with mock.patch.object(
                exporting_module,
                "_inspect_for_publication",
                side_effect=fail_for_published_target,
            ), mock.patch.object(
                exporting_module, "_atomic_swap", side_effect=fail_restoration
            ):
                with self.assertRaisesRegex(
                    ExportPublicationError, "recovery evidence is preserved"
                ):
                    publish_staged_directory(
                        destination=str(destination),
                        expected_state=reviewed,
                        producer=self._producer,
                    )
            evidence = list(base.glob(".glyphs-mcp-v2-export-*"))
            self.assertEqual(len(evidence), 1)
            self.assertEqual(
                (evidence[0] / "bundle" / "old.txt").read_text(encoding="utf-8"),
                "old",
            )


if __name__ == "__main__":
    unittest.main()
