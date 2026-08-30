"""Stable one-pass saved-source contracts for the v2 change Reporter."""

from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.background_work import BackgroundWorkCoordinator  # noqa: E402
from glyphs_mcp_v2.saved_source import (  # noqa: E402
    SavedSourceReader,
    SavedSourceService,
    SavedSourceStore,
    normalize_source_path,
    saved_source_signature,
)


FLAT_FIXTURE = REPO / "GlyphsSDK/GlyphsFileFormat/GlyphsFileFormatv3.glyphs"
PACKAGE_FIXTURE = REPO / "GlyphsSDK/GlyphsFileFormat/GlyphsFileFormatv3.glyphspackage"


class SavedSourceTests(unittest.TestCase):
    def test_flat_refresh_reads_the_source_bytes_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "Family.glyphs"
            shutil.copy2(FLAT_FIXTURE, target)
            reads: list[Path] = []

            def read_bytes(path: Path) -> bytes:
                reads.append(path)
                return Path.read_bytes(path)

            store = SavedSourceStore(
                reader=SavedSourceReader(read_bytes=read_bytes)
            )
            result = store.refresh(target)

            self.assertTrue(result.changed)
            self.assertIsNotNone(result.snapshot)
            self.assertEqual(reads, [target])
            self.assertEqual(
                result.snapshot.source_fingerprint,
                "sha256:86ba946d125a404e6bb9ccce992b832c93f81bf16edf5895969ac615acd5baa8",
            )

    def test_package_refresh_reads_each_source_file_once(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "Family.glyphspackage"
            shutil.copytree(PACKAGE_FIXTURE, target)
            reads: list[str] = []

            def read_bytes(path: Path) -> bytes:
                reads.append(path.relative_to(target).as_posix())
                return Path.read_bytes(path)

            result = SavedSourceStore(
                reader=SavedSourceReader(read_bytes=read_bytes)
            ).refresh(target)
            expected = [record[0] for record in saved_source_signature(target)[2]]

            self.assertIsNotNone(result.snapshot)
            self.assertEqual(sorted(reads), sorted(expected))
            self.assertEqual(len(reads), len(set(reads)))

    def test_source_changed_during_read_is_never_published(self) -> None:
        signatures = iter(
            (
                ("glyphs", True, 1, 10, 1),
                ("glyphs", True, 1, 10, 2),
            )
        )
        reader = SavedSourceReader(
            signature=lambda _path: next(signatures),
            read_bytes=lambda _path: FLAT_FIXTURE.read_bytes(),
        )

        result = SavedSourceStore(reader=reader).refresh("/fonts/Family.glyphs")

        self.assertFalse(result.changed)
        self.assertIsNone(result.snapshot)
        self.assertEqual(result.error, "source_changed_during_read")

    def test_decode_failure_retains_the_last_valid_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "Family.glyphs"
            shutil.copy2(FLAT_FIXTURE, target)
            store = SavedSourceStore()
            self.assertIsNotNone(store.refresh(target).snapshot)
            target.write_text("not a Glyphs property list", encoding="utf-8")

            result = store.refresh(target)

            self.assertFalse(result.changed)
            self.assertIsNotNone(store.snapshot(target))
            self.assertIs(result.snapshot, store.snapshot(target))
            self.assertEqual(result.error, "source_decode_failed")

    def test_equal_content_reuses_one_canonical_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            first = Path(root) / "First.glyphs"
            second = Path(root) / "Second.glyphs"
            shutil.copy2(FLAT_FIXTURE, first)
            shutil.copy2(FLAT_FIXTURE, second)
            store = SavedSourceStore()
            first_snapshot = store.refresh(first).snapshot
            second_snapshot = store.refresh(second).snapshot

            self.assertIsNotNone(first_snapshot)
            self.assertIsNotNone(second_snapshot)
            self.assertIs(first_snapshot.canonical, second_snapshot.canonical)

    def test_retain_only_evicts_closed_or_save_as_paths(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            first = Path(root) / "First.glyphs"
            second = Path(root) / "Second.glyphs"
            shutil.copy2(FLAT_FIXTURE, first)
            shutil.copy2(FLAT_FIXTURE, second)
            store = SavedSourceStore()
            store.refresh(first)
            store.refresh(second)

            self.assertTrue(store.retain_only({str(second)}))
            self.assertIsNone(store.snapshot(first))
            self.assertIsNotNone(store.snapshot(second))

    def test_close_and_save_as_eviction_is_enqueued(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            first = Path(root) / "First.glyphs"
            second = Path(root) / "Second.glyphs"
            shutil.copy2(FLAT_FIXTURE, first)
            shutil.copy2(FLAT_FIXTURE, second)
            coordinator = BackgroundWorkCoordinator(thread_name="source-eviction")
            service = SavedSourceService(coordinator=coordinator)
            service.store.refresh(first)
            service.store.refresh(second)
            completed = threading.Event()
            try:
                generation = service.request_retain_only(
                    {str(second)}, completed=lambda _changed: completed.set()
                )
                self.assertIsNotNone(generation)
                self.assertTrue(completed.wait(1.0))
                self.assertIsNone(service.store.snapshot(first))
                self.assertIsNotNone(service.store.snapshot(second))
            finally:
                coordinator.close(wait=True)

    def test_manual_service_refresh_is_asynchronous(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "Family.glyphs"
            shutil.copy2(FLAT_FIXTURE, target)
            coordinator = BackgroundWorkCoordinator(thread_name="saved-source-test")
            service = SavedSourceService(coordinator=coordinator)
            completed = threading.Event()
            service.subscribe(lambda _result: completed.set())
            try:
                generation = service.request_refresh(target, force=True)
                self.assertIsNotNone(generation)
                self.assertTrue(completed.wait(2.0))
                self.assertIsNotNone(service.store.snapshot(target))
            finally:
                coordinator.close(wait=True)

    def test_refresh_submission_performs_no_signature_or_file_io(self) -> None:
        started = threading.Event()
        release = threading.Event()
        signature_threads: list[int | None] = []

        def signature(_path: Path):
            signature_threads.append(threading.current_thread().ident)
            started.set()
            release.wait(2.0)
            return ("glyphs", False, None, None, None)

        coordinator = BackgroundWorkCoordinator(thread_name="saved-source-boundary")
        service = SavedSourceService(
            store=SavedSourceStore(reader=SavedSourceReader(signature=signature)),
            coordinator=coordinator,
        )
        try:
            before = time.monotonic()
            generation = service.request_refresh("/fonts/Family.glyphs", force=True)
            elapsed = time.monotonic() - before
            self.assertIsNotNone(generation)
            self.assertLess(elapsed, 0.05)
            self.assertTrue(started.wait(1.0))
            self.assertEqual(signature_threads, [coordinator.worker.ident])
        finally:
            release.set()
            coordinator.close(wait=True)

    def test_metadata_signatures_track_flat_and_package_changes(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            flat = Path(root) / "Family.glyphs"
            flat.write_text("one", encoding="utf-8")
            flat_before = saved_source_signature(flat)
            flat.write_text("longer", encoding="utf-8")
            self.assertNotEqual(saved_source_signature(flat), flat_before)

            package = Path(root) / "Family.glyphspackage"
            glyphs = package / "glyphs"
            glyphs.mkdir(parents=True)
            glyph = glyphs / "A.glyph"
            glyph.write_text("one", encoding="utf-8")
            package_before = saved_source_signature(package)
            glyph.write_text("longer", encoding="utf-8")
            self.assertNotEqual(saved_source_signature(package), package_before)

    def test_only_saved_glyphs_source_paths_are_accepted(self) -> None:
        self.assertTrue(normalize_source_path("Family.glyphs").endswith("Family.glyphs"))
        self.assertTrue(
            normalize_source_path("Family.glyphspackage").endswith(
                "Family.glyphspackage"
            )
        )
        self.assertIsNone(normalize_source_path("Family.ufo"))
        self.assertIsNone(normalize_source_path(None))


if __name__ == "__main__":
    unittest.main()
