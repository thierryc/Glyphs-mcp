"""Smoke tests for the installer script.

These tests avoid touching the real Glyphs user folders by setting HOME to a
temporary directory. They also avoid invoking pip installs; we only validate
sorting logic, CLI validation, and plugin/skill installation behavior.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
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
    def assert_parser_error(self, argv: list[str], expected: str) -> None:
        install_cli = _load_install_cli()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as ctx:
                install_cli.parse_cli_options(argv)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn(expected, stderr.getvalue())

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

    def test_main_without_flags_uses_interactive_flow(self) -> None:
        install_cli = _load_install_cli()
        calls: list[Path] = []
        original_run_interactive = install_cli.run_interactive
        original_run_non_interactive = install_cli.run_non_interactive
        try:
            install_cli.run_interactive = lambda requirements: calls.append(requirements)
            install_cli.run_non_interactive = lambda options, requirements: self.fail("non-interactive flow should not be used")
            install_cli.main([])
        finally:
            install_cli.run_interactive = original_run_interactive
            install_cli.run_non_interactive = original_run_non_interactive

        self.assertEqual(calls, [_repo_root() / "requirements.txt"])

    def test_non_interactive_requires_python_mode_and_plugin_mode(self) -> None:
        self.assert_parser_error(
            ["--non-interactive"],
            "--non-interactive requires --python-mode and --plugin-mode.",
        )

    def test_custom_python_mode_requires_python_path(self) -> None:
        self.assert_parser_error(
            ["--non-interactive", "--python-mode", "custom", "--plugin-mode", "copy", "--skip-skills"],
            "--python-path is required when --python-mode custom is used.",
        )

    def test_install_skills_requires_target_in_non_interactive_mode(self) -> None:
        self.assert_parser_error(
            ["--non-interactive", "--python-mode", "glyphs", "--plugin-mode", "copy", "--install-skills"],
            "--install-skills requires --skills-target in non-interactive mode.",
        )

    def test_programmatic_link_mode_installs_plugin_as_symlink(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks not supported on this platform")

        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            original_resolve_python = install_cli.resolve_python_selection_non_interactive
            original_show_guidance = install_cli.show_client_guidance
            try:
                install_cli.resolve_python_selection_non_interactive = lambda options, requirements: None
                install_cli.show_client_guidance = lambda: self.fail("client guidance should not run")
                options = install_cli.InstallerOptions(
                    non_interactive=True,
                    python_mode="glyphs",
                    plugin_mode="link",
                    install_skills=False,
                    overwrite_plugin=False,
                    show_client_guidance=False,
                )
                install_cli.run_non_interactive(options, _repo_root() / "requirements.txt")
            except OSError as e:
                self.skipTest(f"symlink creation not permitted: {e}")
            finally:
                install_cli.resolve_python_selection_non_interactive = original_resolve_python
                install_cli.show_client_guidance = original_show_guidance
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
            self.assertTrue(dest.is_symlink())

    def test_run_non_interactive_requires_plugin_policy_when_plugin_exists(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            original_resolve_python = install_cli.resolve_python_selection_non_interactive
            try:
                dest = (
                    Path(tmp)
                    / "Library"
                    / "Application Support"
                    / "Glyphs 3"
                    / "Plugins"
                    / "Glyphs MCP.glyphsPlugin"
                )
                dest.mkdir(parents=True, exist_ok=True)
                install_cli.resolve_python_selection_non_interactive = lambda options, requirements: None
                options = install_cli.InstallerOptions(
                    non_interactive=True,
                    python_mode="glyphs",
                    plugin_mode="copy",
                    install_skills=False,
                    overwrite_plugin=None,
                    show_client_guidance=False,
                )
                with self.assertRaises(SystemExit) as ctx:
                    install_cli.run_non_interactive(options, _repo_root() / "requirements.txt")
            finally:
                install_cli.resolve_python_selection_non_interactive = original_resolve_python
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

        self.assertEqual(str(ctx.exception), "Existing plug-in installation found. Re-run with --overwrite-plugin or --keep-plugin.")

    def test_install_skill_bundle_copies_managed_skills_only(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                unrelated = Path(tmp) / ".codex" / "skills" / "third-party-skill"
                unrelated.mkdir(parents=True, exist_ok=True)
                (unrelated / "SKILL.md").write_text("# third-party\n", encoding="utf-8")

                installed, skipped = install_cli.install_skill_bundle(install_cli.codex_skills_dir())
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertFalse(skipped)
            self.assertGreaterEqual(len(installed), 1)
            for skill_name in installed:
                self.assertTrue(skill_name.startswith("glyphs-mcp-"))
                self.assertTrue((Path(tmp) / ".codex" / "skills" / skill_name / "SKILL.md").is_file())
            self.assertTrue((Path(tmp) / ".codex" / "skills" / "third-party-skill" / "SKILL.md").is_file())

    def test_install_skill_bundle_overwrites_managed_skills_only_when_requested(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                dest_root = install_cli.claude_code_skills_dir()
                managed_dest = dest_root / "glyphs-mcp-connect"
                managed_dest.mkdir(parents=True, exist_ok=True)
                (managed_dest / "SKILL.md").write_text("old managed skill\n", encoding="utf-8")

                unrelated = dest_root / "another-skill"
                unrelated.mkdir(parents=True, exist_ok=True)
                (unrelated / "SKILL.md").write_text("keep me\n", encoding="utf-8")

                installed, skipped = install_cli.install_skill_bundle(dest_root, overwrite_existing=True)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertIn("glyphs-mcp-connect", installed)
            self.assertFalse(skipped)
            self.assertIn("name: glyphs-mcp-connect", (managed_dest / "SKILL.md").read_text(encoding="utf-8"))
            self.assertEqual((unrelated / "SKILL.md").read_text(encoding="utf-8"), "keep me\n")

    def test_programmatic_skill_install_targets_codex_only(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                installed = install_cli.install_skill_bundle_for_targets(
                    install_cli.skill_targets_from_option("codex"),
                    overwrite_existing=False,
                    non_interactive=True,
                )
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertTrue(installed)
            self.assertTrue((Path(tmp) / ".codex" / "skills" / "glyphs-mcp-connect" / "SKILL.md").is_file())
            self.assertFalse((Path(tmp) / ".claude" / "skills").exists())

    def test_programmatic_skill_install_targets_claude_only(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                installed = install_cli.install_skill_bundle_for_targets(
                    install_cli.skill_targets_from_option("claude"),
                    overwrite_existing=False,
                    non_interactive=True,
                )
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertTrue(installed)
            self.assertTrue((Path(tmp) / ".claude" / "skills" / "glyphs-mcp-connect" / "SKILL.md").is_file())
            self.assertFalse((Path(tmp) / ".codex" / "skills").exists())

    def test_programmatic_skill_install_targets_both(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                installed = install_cli.install_skill_bundle_for_targets(
                    install_cli.skill_targets_from_option("both"),
                    overwrite_existing=False,
                    non_interactive=True,
                )
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertTrue(installed)
            self.assertTrue((Path(tmp) / ".codex" / "skills" / "glyphs-mcp-connect" / "SKILL.md").is_file())
            self.assertTrue((Path(tmp) / ".claude" / "skills" / "glyphs-mcp-connect" / "SKILL.md").is_file())

    def test_install_skill_bundle_for_targets_requires_policy_when_managed_skills_exist(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                managed_dest = install_cli.codex_skills_dir() / "glyphs-mcp-connect"
                managed_dest.mkdir(parents=True, exist_ok=True)
                (managed_dest / "SKILL.md").write_text("old managed skill\n", encoding="utf-8")
                with self.assertRaises(SystemExit) as ctx:
                    install_cli.install_skill_bundle_for_targets(
                        install_cli.skill_targets_from_option("codex"),
                        overwrite_existing=None,
                        non_interactive=True,
                    )
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

        self.assertEqual(
            str(ctx.exception),
            f"Existing Glyphs MCP skills in {managed_dest.parent} found. Re-run with --overwrite-skills or --keep-skills.",
        )

    def test_existing_managed_skills_are_overwritten_when_requested(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                dest_root = install_cli.codex_skills_dir()
                managed_dest = dest_root / "glyphs-mcp-connect"
                managed_dest.mkdir(parents=True, exist_ok=True)
                (managed_dest / "SKILL.md").write_text("old managed skill\n", encoding="utf-8")
                install_cli.install_skill_bundle_for_targets(
                    install_cli.skill_targets_from_option("codex"),
                    overwrite_existing=True,
                    non_interactive=True,
                )
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertIn("name: glyphs-mcp-connect", (managed_dest / "SKILL.md").read_text(encoding="utf-8"))

    def test_existing_managed_skills_are_kept_when_requested(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                dest_root = install_cli.codex_skills_dir()
                managed_dest = dest_root / "glyphs-mcp-connect"
                managed_dest.mkdir(parents=True, exist_ok=True)
                (managed_dest / "SKILL.md").write_text("old managed skill\n", encoding="utf-8")
                install_cli.install_skill_bundle_for_targets(
                    install_cli.skill_targets_from_option("codex"),
                    overwrite_existing=False,
                    non_interactive=True,
                )
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertEqual((managed_dest / "SKILL.md").read_text(encoding="utf-8"), "old managed skill\n")

    def test_existing_plugin_is_replaced_when_overwrite_is_requested(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                dest = (
                    Path(tmp)
                    / "Library"
                    / "Application Support"
                    / "Glyphs 3"
                    / "Plugins"
                    / "Glyphs MCP.glyphsPlugin"
                )
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "marker.txt").write_text("old plugin\n", encoding="utf-8")
                install_cli.install_plugin(mode="copy", overwrite_existing=True)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertFalse((dest / "marker.txt").exists())
            self.assertTrue((dest / "Contents" / "Resources" / "plugin.py").is_file())

    def test_existing_plugin_is_kept_when_requested(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                dest = (
                    Path(tmp)
                    / "Library"
                    / "Application Support"
                    / "Glyphs 3"
                    / "Plugins"
                    / "Glyphs MCP.glyphsPlugin"
                )
                dest.mkdir(parents=True, exist_ok=True)
                marker = dest / "marker.txt"
                marker.write_text("old plugin\n", encoding="utf-8")
                changed = install_cli.install_plugin(mode="copy", overwrite_existing=False)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertFalse(changed)
            self.assertEqual(marker.read_text(encoding="utf-8"), "old plugin\n")


if __name__ == "__main__":
    unittest.main()
