"""Contracts for version-neutral Glyphs native exporter invocation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.native_export import (  # noqa: E402
    NativeExportError,
    invoke_native_export,
    normalize_export_result,
)


class NativeExportTests(unittest.TestCase):
    def test_lowercase_glyphs4_keywords_and_none_success(self) -> None:
        calls = []

        def generate(*, fontPath, containers):
            calls.append((fontPath, containers))
            return None

        result = invoke_native_export(
            generate, fontPath="/tmp/export", containers=["plain"]
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["keywordSpelling"], "lowercase")
        self.assertEqual(calls, [("/tmp/export", ["plain"])])

    def test_legacy_capitalized_keywords_are_selected_before_invocation(self) -> None:
        calls = []

        def generate(*, FontPath, Containers):
            calls.append((FontPath, Containers))
            return True

        result = invoke_native_export(
            generate, fontPath="/tmp/export", containers=["plain"]
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["keywordSpelling"], "legacy_capitalized")
        self.assertEqual(len(calls), 1)

    def test_false_strings_and_mixed_batch_fail(self) -> None:
        for value in (False, "export failed", [None, "second failed"]):
            with self.subTest(value=value), self.assertRaises(NativeExportError):
                normalize_export_result(value)

    def test_documented_and_native_success_variants_pass(self) -> None:
        for value in (True, None, [True, None], (None,)):
            with self.subTest(value=value):
                self.assertTrue(normalize_export_result(value)["success"])

    def test_unknown_exporter_result_is_strict(self) -> None:
        with self.assertRaisesRegex(NativeExportError, "unsupported result type"):
            normalize_export_result({"ok": True})


if __name__ == "__main__":
    unittest.main()
