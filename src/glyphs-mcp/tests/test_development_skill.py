"""Tests for the workspace-first Glyphs development skill scaffolder."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import sys
import tempfile
from types import ModuleType
import unittest


REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / "skills" / "glyphs-mcp-development"
SCAFFOLDER = SKILL / "scripts" / "scaffold.py"


def _load_scaffolder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("glyphs_development_scaffold", SCAFFOLDER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


class DevelopmentSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_scaffolder()

    def _run(self, argv: list[str]) -> tuple[int, dict]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = self.module.main(argv)
        stream = stdout.getvalue() if result == 0 else stderr.getvalue()
        return result, json.loads(stream)

    def test_script_scaffold_is_valid_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyphs-development-script.") as tmp:
            args = [
                "create",
                "script",
                "--name",
                "Audit Selected Glyphs",
                "--description",
                "Audit selected layers.",
                "--destination",
                tmp,
            ]
            code, payload = self._run(args)
            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["kind"], "script")
            self.assertFalse(payload["runtimeTested"])

            script = Path(tmp) / "Audit Selected Glyphs.py"
            text = script.read_text(encoding="utf-8")
            self.assertIn("# MenuTitle: Audit Selected Glyphs", text)
            self.assertIn("from GlyphsApp import Glyphs", text)

            code, payload = self._run(args)
            self.assertEqual(code, 2)
            self.assertIn("Refusing to overwrite", payload["error"])

    def test_all_supported_plugin_scaffolds_are_complete(self) -> None:
        suffixes = {
            "general": ".glyphsPlugin",
            "reporter": ".glyphsReporter",
            "filter": ".glyphsFilter",
            "palette": ".glyphsPalette",
            "select-tool": ".glyphsTool",
            "file-format": ".glyphsFileFormat",
        }
        with tempfile.TemporaryDirectory(prefix="glyphs-development-plugins.") as tmp:
            for kind, suffix in suffixes.items():
                with self.subTest(kind=kind):
                    class_name = "Test" + kind.replace("-", "").title()
                    code, payload = self._run(
                        [
                            "create",
                            kind,
                            "--name",
                            "Test " + kind,
                            "--class-name",
                            class_name,
                            "--developer",
                            "Glyphs MCP Test",
                            "--destination",
                            tmp,
                        ]
                    )
                    self.assertEqual(code, 0, payload)
                    self.assertTrue(payload["ok"])
                    self.assertEqual(payload["kind"], kind)
                    self.assertEqual(payload["target"], "both")
                    self.assertFalse(payload["runtimeTested"])

                    bundle = Path(payload["artifact"])
                    self.assertTrue(bundle.name.endswith(suffix))
                    plist = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
                    self.assertEqual(plist["NSPrincipalClass"], class_name)
                    self.assertEqual(plist["CFBundleName"], "Test " + kind)
                    self.assertTrue((bundle / "Contents" / "MacOS" / "plugin").is_file())
                    self.assertFalse(self.module._unresolved_placeholders(bundle))

                    validate_code, validated = self._run(
                        ["validate", str(bundle), "--target", "both"]
                    )
                    self.assertEqual(validate_code, 0, validated)
                    self.assertIn("principal-class", validated["checks"])

    def test_palette_scaffold_uses_code_only_ui(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyphs-development-palette.") as tmp:
            code, payload = self._run(
                [
                    "create",
                    "palette",
                    "--name",
                    "Test Palette",
                    "--class-name",
                    "TestPalette",
                    "--developer",
                    "Glyphs MCP Test",
                    "--destination",
                    tmp,
                ]
            )
            self.assertEqual(code, 0, payload)
            resources = Path(payload["artifact"]) / "Contents" / "Resources"
            self.assertFalse((resources / "IBdialog.xib").exists())
            self.assertFalse((resources / "IBdialog.nib").exists())
            self.assertIn("from vanilla import", (resources / "plugin.py").read_text(encoding="utf-8"))

    def test_live_glyphs_destination_requires_explicit_override(self) -> None:
        live = (
            Path.home()
            / "Library"
            / "Application Support"
            / "Glyphs 4"
            / "Plugins"
            / "Unsafe.glyphsPlugin"
        )
        self.assertTrue(self.module._is_live_glyphs_path(live))
        with self.assertRaises(self.module.ScaffoldError):
            self.module._assert_destination_allowed(live, False)
        self.module._assert_destination_allowed(live, True)

    def test_vendored_assets_match_the_pinned_sdk(self) -> None:
        metadata = json.loads((SKILL / "assets" / "SOURCE.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["revision"], "0f5422db727b78cb42abfb386f33ae0b382b0c4d")
        self.assertEqual(metadata["license"], "Apache-2.0")
        self.assertEqual(
            (SKILL / "assets" / "GlyphsSDK-LICENSE.txt").read_bytes(),
            (REPO / "GlyphsSDK" / "LICENSE").read_bytes(),
        )
        for kind, expected_hash in metadata["loaderSha256"].items():
            template_root = SKILL / "assets" / "templates" / kind
            loader = next(template_root.rglob("Contents/MacOS/plugin"))
            self.assertEqual(hashlib.sha256(loader.read_bytes()).hexdigest(), expected_hash)


if __name__ == "__main__":
    unittest.main()
