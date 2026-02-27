"""Smoke tests for the interactive installer script.

These tests avoid touching the real Glyphs user folders by setting HOME to a
temporary directory. They also avoid invoking pip installs; we only validate
sorting logic and plugin copy/symlink behavior.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_install_cli() -> types.ModuleType:
    path = _repo_root() / "src" / "glyphs-mcp" / "scripts" / "install_cli.py"
    spec = importlib.util.spec_from_file_location("glyphs_mcp_install_cli", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Required on Python 3.14+ for dataclasses to resolve the module namespace.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


class InstallerSmokeTests(unittest.TestCase):
    def test_sort_prefers_python_org_on_tie(self) -> None:
        install_cli = _load_install_cli()

        cands = [
            install_cli.PythonCandidate(Path("/opt/homebrew/bin/python3.12"), "3.12.3", "homebrew"),
            install_cli.PythonCandidate(Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"), "3.12.3", "python.org"),
        ]
        install_cli._sort_python_candidates(cands)
        self.assertEqual(cands[0].source, "python.org")

    def test_install_plugin_copy_uses_temp_home(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                install_cli.install_plugin(mode="copy")
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            dest = (
                Path(tmp)
                / "Library"
                / "Application Support"
                / "Glyphs 3"
                / "Plugins"
                / "Glyphs MCP.glyphsPlugin"
            )
            self.assertTrue(dest.is_dir(), f"Expected plugin folder at {dest}")
            self.assertTrue((dest / "Contents" / "Resources" / "plugin.py").is_file())

    def test_install_plugin_symlink_uses_temp_home(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks not supported on this platform")

        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                try:
                    install_cli.install_plugin(mode="link")
                except OSError as e:
                    self.skipTest(f"symlink creation not permitted: {e}")
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            dest = (
                Path(tmp)
                / "Library"
                / "Application Support"
                / "Glyphs 3"
                / "Plugins"
                / "Glyphs MCP.glyphsPlugin"
            )
            self.assertTrue(dest.exists())
            self.assertTrue(dest.is_symlink())

            expected = _repo_root() / "src" / "glyphs-mcp" / "Glyphs MCP.glyphsPlugin"
            self.assertEqual(dest.resolve(), expected.resolve())


if __name__ == "__main__":
    unittest.main()

