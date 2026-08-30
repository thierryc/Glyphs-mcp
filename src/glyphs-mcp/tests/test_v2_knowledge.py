"""Pinned offline Knowledge build, search, citation, and packaging tests."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.knowledge import (  # noqa: E402
    get_knowledge,
    knowledge_manifest,
    load_corpus,
    search_knowledge,
)


class V2KnowledgeTests(unittest.TestCase):
    def test_manifest_is_pinned_offline_and_complete(self) -> None:
        corpus = load_corpus()
        manifest = knowledge_manifest()

        self.assertFalse(manifest["runtimeNetworkRequired"])
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["entryCount"], len(corpus["entries"]))
        self.assertGreaterEqual(manifest["entryCount"], 250)
        self.assertRegex(manifest["glyphsSdkRevision"], r"^[0-9a-f]{40}$")
        self.assertRegex(manifest["corpusFingerprint"], r"^sha256:[0-9a-f]{64}$")
        self.assertLessEqual(
            {
                "spacing",
                "kerning",
                "outlines",
                "anchors",
                "interpolation",
                "variable-fonts",
                "color-fonts",
                "unicode",
                "opentype",
                "export",
                "glyphs-python",
                "plugin-development",
                "file-format",
            },
            set(manifest["topics"]),
        )

    def test_every_entry_has_exact_citation_version_and_checksum_evidence(self) -> None:
        for entry in load_corpus()["entries"]:
            with self.subTest(entry=entry["id"]):
                self.assertTrue(entry["id"])
                self.assertTrue(entry["topics"])
                self.assertTrue(entry["glyphsVersions"])
                self.assertIn(entry["authority"], {"authoritative", "practice", "heuristic"})
                self.assertTrue(entry["verifiedAt"])
                self.assertTrue(entry["sourceRevision"])
                self.assertTrue(entry["citations"])
                citation = entry["citations"][0]
                self.assertEqual(citation["url"], entry["sourceUrl"])
                self.assertEqual(citation["revision"], entry["sourceRevision"])
                digest = "sha256:" + hashlib.sha256(
                    entry["body"].encode("utf-8")
                ).hexdigest()
                self.assertEqual(entry["contentFingerprint"], digest)

    def test_ranked_search_is_deterministic_specific_and_filterable(self) -> None:
        first = search_knowledge("negative sidebearing")
        second = search_knowledge("negative sidebearing")
        self.assertEqual(first, second)
        self.assertEqual(first["items"][0]["id"], "practice.negative-sidebearings")
        self.assertTrue(first["items"][0]["sourceUrl"])

        filtered = search_knowledge(
            "schema layer",
            topics=["file-format"],
            authorities=["authoritative"],
            glyphs_versions=["4"],
        )
        self.assertTrue(filtered["items"])
        self.assertTrue(
            all("file-format" in item["topics"] for item in filtered["items"])
        )
        self.assertTrue(
            all(item["authority"] == "authoritative" for item in filtered["items"])
        )
        self.assertTrue(
            all("4" in item["glyphsVersions"] for item in filtered["items"])
        )

    def test_coding_entries_are_focused_and_suitable_for_python_fallback(self) -> None:
        result = get_knowledge(
            [
                "coding.detached-layer-inspection",
                "coding.detached-width-edit",
                "coding.open-world-ui-boundary",
            ]
        )
        self.assertFalse(result["missingIds"])
        for entry in result["items"]:
            self.assertTrue(entry["examples"])
            self.assertTrue(entry["compatibilityNotes"])
            self.assertIn("glyphs-python", entry["topics"])
        self.assertNotIn(
            "Glyphs.",
            result["items"][0]["examples"][0],
        )
        self.assertIn(
            "Glyphs.font",
            result["items"][2]["examples"][0],
        )

    def test_metrics_key_guidance_is_specific_cited_and_searchable(self) -> None:
        result = search_knowledge(
            "GSLayer syncMetrics same master metrics key",
            topics=["spacing"],
            glyphs_versions=["4"],
        )

        self.assertEqual(
            result["items"][0]["id"],
            "glyphs4.metrics-key-resolution",
        )
        entry = get_knowledge(["glyphs4.metrics-key-resolution"])["items"][0]
        self.assertEqual(entry["glyphsVersions"], ["4"])
        self.assertGreaterEqual(len(entry["citations"]), 3)
        self.assertIn("GSLayer.syncMetrics()", entry["body"])
        self.assertIn("associated master", entry["body"])
        self.assertIn("inheritance.metrics", entry["body"])

    def test_build_check_rejects_source_or_generated_drift(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/build_v2_knowledge.py", "--check"],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Knowledge index is current", result.stdout)

    def test_wheel_configuration_includes_the_offline_index(self) -> None:
        pyproject = tomllib.loads(
            (V2_SOURCE / "pyproject.toml").read_text(encoding="utf-8")
        )
        patterns = pyproject["tool"]["setuptools"]["package-data"]["glyphs_mcp_v2"]
        self.assertIn("knowledge_data/*.json", patterns)
        payload = json.loads(
            (
                V2_SOURCE
                / "glyphs_mcp_v2"
                / "knowledge_data"
                / "index.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(payload["manifest"]["entryCount"], len(payload["entries"]))


if __name__ == "__main__":
    unittest.main()
