"""Saved-source baseline cache contracts for the v2 change Reporter."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.saved_baseline import (  # noqa: E402
    SavedBaselineCache,
    normalize_source_path,
    saved_source_signature,
)


class SavedBaselineCacheTests(unittest.TestCase):
    def test_refresh_publishes_only_decoded_readable_sources(self) -> None:
        state = {
            "signature": ("glyphs", 1),
            "fingerprint": "sha256:first",
            "model": {"glyphs": {"A": {}}},
        }
        calls = {"state": 0, "load": 0}

        def signature(_path):
            return state["signature"]

        def source_state(_path):
            calls["state"] += 1
            return {
                "exists": True,
                "readable": True,
                "contentFingerprint": state["fingerprint"],
            }

        def load_model(_path):
            calls["load"] += 1
            return state["model"]

        cache = SavedBaselineCache(
            signature=signature,
            source_state=source_state,
            load_model=load_model,
        )
        path = "/fonts/Family.glyphs"

        self.assertTrue(cache.refresh(path))
        self.assertEqual(cache.snapshot(path).source_fingerprint, "sha256:first")
        self.assertEqual(calls, {"state": 2, "load": 1})
        self.assertFalse(cache.refresh(path))
        self.assertEqual(calls, {"state": 2, "load": 1})

        state["signature"] = ("glyphs", 2)
        self.assertFalse(cache.refresh(path))
        self.assertEqual(calls, {"state": 3, "load": 1})

        state["signature"] = ("glyphs", 3)
        state["fingerprint"] = "sha256:second"
        state["model"] = {"glyphs": {"B": {}}}
        self.assertTrue(cache.refresh(path))
        self.assertEqual(cache.snapshot(path).model, state["model"])
        self.assertEqual(calls, {"state": 5, "load": 2})

    def test_changed_source_that_fails_decode_clears_the_old_baseline(self) -> None:
        values = {
            "signature": ("glyphs", 1),
            "fingerprint": "sha256:first",
            "model": {"glyphs": {"A": {}}},
        }
        cache = SavedBaselineCache(
            signature=lambda _path: values["signature"],
            source_state=lambda _path: {
                "exists": True,
                "readable": True,
                "contentFingerprint": values["fingerprint"],
            },
            load_model=lambda _path: values["model"],
        )
        path = "/fonts/Family.glyphs"
        self.assertTrue(cache.refresh(path))

        values.update(
            signature=("glyphs", 2),
            fingerprint="sha256:broken",
            model=None,
        )
        self.assertTrue(cache.refresh(path))
        self.assertIsNone(cache.snapshot(path))
        self.assertFalse(cache.refresh(path))

    def test_source_changed_during_decode_is_not_published(self) -> None:
        fingerprints = iter(("sha256:before", "sha256:after"))
        cache = SavedBaselineCache(
            signature=lambda _path: ("glyphs", 1),
            source_state=lambda _path: {
                "exists": True,
                "readable": True,
                "contentFingerprint": next(fingerprints),
            },
            load_model=lambda _path: {"glyphs": {"A": {}}},
        )

        self.assertFalse(cache.refresh("/fonts/Family.glyphs"))
        self.assertIsNone(cache.snapshot("/fonts/Family.glyphs"))

    def test_retain_only_evicts_closed_or_save_as_paths(self) -> None:
        cache = SavedBaselineCache(
            signature=lambda path: (path.name, 1),
            source_state=lambda path: {
                "exists": True,
                "readable": True,
                "contentFingerprint": "sha256:{}".format(path.name),
            },
            load_model=lambda path: {"path": path.name},
        )
        first = "/fonts/First.glyphs"
        second = "/fonts/Second.glyphs"
        cache.refresh(first)
        cache.refresh(second)

        self.assertTrue(cache.retain_only({second}))
        self.assertIsNone(cache.snapshot(first))
        self.assertIsNotNone(cache.snapshot(second))
        self.assertFalse(cache.retain_only({second}))

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
