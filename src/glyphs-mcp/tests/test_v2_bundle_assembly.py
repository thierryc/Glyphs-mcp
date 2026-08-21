"""Deterministic, worktree-contained v2 runtime payload assembly tests."""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
BUILDER = REPO / "scripts" / "build_v2_runtime_payload.py"
PACKAGE_RELATIVE = Path("Glyphs MCP.glyphsPlugin/Contents/Resources/glyphs_mcp_v2")
BUNDLE_RELATIVE = Path("Glyphs MCP.glyphsPlugin")


def _file_map(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class V2BundleAssemblyTests(unittest.TestCase):
    def test_builder_assembles_identical_payloads_inside_the_worktree(self) -> None:
        temporary_root = REPO / ".tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="v2-payload-test-", dir=temporary_root) as tmp:
            output = Path(tmp) / "payload"
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [sys.executable, str(BUILDER), "--output-root", str(output)],
                cwd=REPO,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            source = output / "source" / PACKAGE_RELATIVE
            plugin_manager = output / "plugin-manager" / PACKAGE_RELATIVE
            self.assertEqual(_file_map(source), _file_map(plugin_manager))
            self.assertNotIn("__pycache__", {part for path in source.rglob("*") for part in path.parts})

            for layout in ("source", "plugin-manager"):
                bundle = output / layout / BUNDLE_RELATIVE
                resources = bundle / "Contents" / "Resources"
                self.assertTrue((bundle / "Contents" / "MacOS" / "plugin").is_file())
                with (bundle / "Contents" / "Info.plist").open("rb") as plist_file:
                    info = plistlib.load(plist_file)
                self.assertEqual(info["CFBundleShortVersionString"], "2.0.0.dev1")
                self.assertEqual(info["CFBundleVersion"], "2.0.0.dev1")

                runtime_bridge = (resources / "mcp_tools.py").read_text(encoding="utf-8")
                self.assertIn(
                    "from glyphs_mcp_v2.runtime import create_glyphs_server",
                    runtime_bridge,
                )
                self.assertNotIn("mcp_tools_annotations", runtime_bridge)

                plugin_entry = (resources / "plugin.py").read_text(encoding="utf-8")
                self.assertIn("from mcp_tools import mcp", plugin_entry)
                self.assertIn("GlyphsMCPChangeDiffReporter", plugin_entry)
                self.assertIn("GlyphsMCPInspectorPalette", plugin_entry)
                self.assertNotIn("GlyphsMCPCandidateReporter", plugin_entry)
                self.assertNotIn("GlyphsMCPLitSquareMetadataPalette", plugin_entry)
                self.assertNotIn("import code_execution", plugin_entry)
                self.assertNotIn("import documentation_resources", plugin_entry)
                self.assertNotIn("import kerning_resources", plugin_entry)

                changes_bridge = (resources / "document_changes_panel.py").read_text(encoding="utf-8")
                self.assertIn("glyphs_mcp_v2.change_log_panel", changes_bridge)
                self.assertTrue((resources / "glyphs_mcp_v2" / "change_diff_reporter.py").is_file())
                inspector = resources / "glyphs_mcp_v2" / "inspector_palette.py"
                self.assertTrue(inspector.is_file())
                inspector_source = inspector.read_text(encoding="utf-8")
                self.assertIn('PALETTE_NAME = "Glyphs MCP"', inspector_source)
                self.assertIn("GlyphsMCPLitSquareMetadataPalette", inspector_source)

                self.assertIn("GlyphsMCPChangeDiffReporter", info["Principal Classes"])
                self.assertIn("GlyphsMCPInspectorPalette", info["Principal Classes"])
                self.assertNotIn("GlyphsMCPCandidateReporter", info["Principal Classes"])
                self.assertNotIn("GlyphsMCPLitSquareMetadataPalette", info["Principal Classes"])

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["fileCount"], len(_file_map(source)))
            self.assertEqual(set(manifest["files"]), set(_file_map(source)))

    def test_builder_rejects_output_outside_the_worktree(self) -> None:
        result = subprocess.run(
            [sys.executable, str(BUILDER), "--output-root", "/private/tmp/glyphs-mcp-v2-escape"],
            cwd=REPO,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must remain inside", result.stderr)


if __name__ == "__main__":
    unittest.main()
