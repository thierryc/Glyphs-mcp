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

    def test_runtime_verification_requires_pyobjc_bridge_modules(self) -> None:
        install_cli = _load_install_cli()

        self.assertIn("objc", install_cli.REQUIRED_RUNTIME_MODULES)
        self.assertIn("Foundation", install_cli.REQUIRED_RUNTIME_MODULES)
        self.assertIn("AppKit", install_cli.REQUIRED_RUNTIME_MODULES)
        self.assertIn("pkg_resources", install_cli.REQUIRED_RUNTIME_MODULES)

    def test_glyphs_preferences_domain_matches_major_version(self) -> None:
        install_cli = _load_install_cli()

        self.assertEqual(install_cli.glyphs_preferences_domain(), "com.GeorgSeifert.Glyphs4")
        self.assertEqual(install_cli.glyphs_preferences_domain("3"), "com.GeorgSeifert.Glyphs3")
        self.assertEqual(install_cli.glyphs_preferences_domain("4"), "com.GeorgSeifert.Glyphs4")

    def test_plugin_site_packages_path_can_target_glyphs_4(self) -> None:
        plugin_path = (
            _repo_root()
            / "src"
            / "glyphs-mcp"
            / "Glyphs MCP.glyphsPlugin"
            / "Contents"
            / "Resources"
            / "plugin.py"
        )
        prefix = plugin_path.read_text(encoding="utf-8").split("\ndef _ensure_user_site_packages_on_path", 1)[0]
        namespace: dict[str, object] = {"__file__": str(plugin_path)}

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-plugin-home.") as tmp:
            old_home = os.environ.get("HOME")
            old_version = os.environ.get("GLYPHS_MCP_GLYPHS_VERSION")
            os.environ["HOME"] = tmp
            os.environ["GLYPHS_MCP_GLYPHS_VERSION"] = "4"
            try:
                exec(compile(prefix, str(plugin_path), "exec"), namespace)
                site_packages = namespace["_glyphs_user_site_packages"]()
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home
                if old_version is None:
                    os.environ.pop("GLYPHS_MCP_GLYPHS_VERSION", None)
                else:
                    os.environ["GLYPHS_MCP_GLYPHS_VERSION"] = old_version

        self.assertEqual(
            site_packages,
            Path(tmp) / "Library" / "Application Support" / "Glyphs 4" / "Scripts" / "site-packages",
        )

    def test_install_plugin_copy_uses_temp_home(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                install_cli.install_plugin(mode="copy", sign_executable=False)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            dest = (
                Path(tmp)
                / "Library"
                / "Application Support"
                / "Glyphs 4"
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
                    install_cli.install_plugin(mode="link", sign_executable=False)
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
                / "Glyphs 4"
                / "Plugins"
                / "Glyphs MCP.glyphsPlugin"
            )
            self.assertTrue(dest.exists())
            self.assertTrue(dest.is_symlink())

            expected = _repo_root() / "src" / "glyphs-mcp" / "Glyphs MCP.glyphsPlugin"
            self.assertEqual(dest.resolve(), expected.resolve())

    def test_install_plugin_symlink_can_target_glyphs_4(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks not supported on this platform")

        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                try:
                    install_cli.install_plugin(mode="link", glyphs_version="4", sign_executable=False)
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
                / "Glyphs 4"
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
            install_cli.run_interactive = lambda requirements, options=None: calls.append(requirements)
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

    def test_non_interactive_skip_deps_does_not_require_python_mode(self) -> None:
        install_cli = _load_install_cli()

        options = install_cli.parse_cli_options(
            [
                "--non-interactive",
                "--glyphs-version",
                "4",
                "--skip-deps",
                "--plugin-mode",
                "link",
                "--skip-skills",
                "--overwrite-plugin",
                "--skip-client-guidance",
            ]
        )

        self.assertTrue(options.skip_deps)
        self.assertEqual(options.glyphs_version, "4")
        self.assertIsNone(options.python_mode)
        self.assertEqual(options.plugin_mode, "link")

    def test_custom_python_mode_requires_python_path(self) -> None:
        self.assert_parser_error(
            ["--non-interactive", "--python-mode", "custom", "--plugin-mode", "copy", "--skip-skills"],
            "--python-path is required when --python-mode custom is used.",
        )

    def test_custom_python_version_gate_allows_312_313_314_and_blocks_315(self) -> None:
        install_cli = _load_install_cli()
        requirements = _repo_root() / "requirements.txt"
        installed: list[tuple[str, Path, Path]] = []
        current_version = ""

        original_python_version = install_cli.python_version
        original_install_custom = install_cli.install_with_custom_python

        def fake_python_version(_python: Path) -> str:
            return current_version

        def fake_install_custom(python: Path, req: Path) -> None:
            installed.append((current_version, python, req))

        try:
            install_cli.python_version = fake_python_version
            install_cli.install_with_custom_python = fake_install_custom

            for current_version in ["3.12.0", "3.13.0", "3.14.0"]:
                options = install_cli.InstallerOptions(
                    non_interactive=True,
                    python_mode="custom",
                    python_path=Path(f"/tmp/python-{current_version}"),
                    plugin_mode="copy",
                    install_skills=False,
                )
                install_cli.resolve_python_selection_non_interactive(options, requirements)

            current_version = "3.15.0"
            options = install_cli.InstallerOptions(
                non_interactive=True,
                python_mode="custom",
                python_path=Path("/tmp/python-3.15.0"),
                plugin_mode="copy",
                install_skills=False,
            )
            with self.assertRaises(SystemExit) as ctx:
                install_cli.resolve_python_selection_non_interactive(options, requirements)
        finally:
            install_cli.python_version = original_python_version
            install_cli.install_with_custom_python = original_install_custom

        self.assertEqual([version for version, _python, _req in installed], ["3.12.0", "3.13.0", "3.14.0"])
        self.assertTrue(all(req == requirements for _version, _python, req in installed))
        self.assertIn("3.11–3.14", str(ctx.exception))

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
            original_sign = install_cli.sign_plugin_executable
            signed: list[Path] = []
            try:
                install_cli.resolve_python_selection_non_interactive = lambda options, requirements: None
                install_cli.show_client_guidance = lambda: self.fail("client guidance should not run")
                install_cli.sign_plugin_executable = lambda bundle: signed.append(bundle)
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
                install_cli.sign_plugin_executable = original_sign
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            dest = (
                Path(tmp)
                / "Library"
                / "Application Support"
                / "Glyphs 4"
                / "Plugins"
                / "Glyphs MCP.glyphsPlugin"
            )
            self.assertTrue(dest.is_symlink())
            self.assertEqual(signed, [dest])

    def test_programmatic_glyphs_4_skip_deps_link_installs_plugin_as_symlink(self) -> None:
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks not supported on this platform")

        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            original_show_guidance = install_cli.show_client_guidance
            original_sign = install_cli.sign_plugin_executable
            signed: list[Path] = []
            try:
                install_cli.show_client_guidance = lambda: self.fail("client guidance should not run")
                install_cli.sign_plugin_executable = lambda bundle: signed.append(bundle)
                options = install_cli.InstallerOptions(
                    non_interactive=True,
                    glyphs_version="4",
                    skip_deps=True,
                    plugin_mode="link",
                    install_skills=False,
                    overwrite_plugin=False,
                    show_client_guidance=False,
                )
                install_cli.run_non_interactive(options, _repo_root() / "requirements.txt")
            except OSError as e:
                self.skipTest(f"symlink creation not permitted: {e}")
            finally:
                install_cli.show_client_guidance = original_show_guidance
                install_cli.sign_plugin_executable = original_sign
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            dest = (
                Path(tmp)
                / "Library"
                / "Application Support"
                / "Glyphs 4"
                / "Plugins"
                / "Glyphs MCP.glyphsPlugin"
            )
            self.assertTrue(dest.is_symlink())
            self.assertEqual(signed, [dest])

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
                    / "Glyphs 4"
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
                    / "Glyphs 4"
                    / "Plugins"
                    / "Glyphs MCP.glyphsPlugin"
                )
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "marker.txt").write_text("old plugin\n", encoding="utf-8")
                install_cli.install_plugin(mode="copy", overwrite_existing=True, sign_executable=False)
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
                    / "Glyphs 4"
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

    def test_install_with_glyphs_python_forces_binary_reinstall(self) -> None:
        install_cli = _load_install_cli()
        calls: list[list[str]] = []
        old_home = os.environ.get("HOME")
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            os.environ["HOME"] = tmp
            fake_bin = Path(tmp) / "GlyphsPythonPlugin" / "bin"
            fake_bin.mkdir(parents=True)
            fake_pip = fake_bin / "pip3"
            fake_python = fake_bin / "python3"
            fake_pip.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_python.write_text("#!/bin/sh\n", encoding="utf-8")
            original_run = install_cli.run
            original_pip = install_cli.glyphs_python_pip
            original_selected_python = install_cli.glyphs_selected_python_bin
            original_verify = install_cli.verify_runtime
            try:
                install_cli.run = lambda cmd: calls.append(cmd)
                install_cli.glyphs_selected_python_bin = lambda glyphs_version="4": None
                install_cli.glyphs_python_pip = lambda glyphs_version="4": fake_pip
                install_cli.verify_runtime = lambda *args, **kwargs: True
                install_cli.install_with_glyphs_python(_repo_root() / "requirements.txt")
            finally:
                install_cli.run = original_run
                install_cli.glyphs_python_pip = original_pip
                install_cli.glyphs_selected_python_bin = original_selected_python
                install_cli.verify_runtime = original_verify
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

        target = (
            Path(tmp)
            / "Library"
            / "Application Support"
            / "Glyphs 4"
            / "Scripts"
            / "site-packages"
        )
        self.assertEqual(calls[0], [str(fake_pip), "install", "--upgrade", "pip"])
        self.assertEqual(
            calls[1],
            [
                str(fake_pip),
                "install",
                "--upgrade",
                "--force-reinstall",
                "--no-compile",
                "--only-binary=:all:",
                "--target",
                str(target),
                "-r",
                str(_repo_root() / "requirements.txt"),
            ],
        )

    def test_install_with_glyphs_python_uses_selected_python_for_glyphs_4(self) -> None:
        install_cli = _load_install_cli()
        calls: list[list[str]] = []
        verify_calls: list[tuple[Path, Path]] = []
        old_home = os.environ.get("HOME")
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            os.environ["HOME"] = tmp
            selected_python = Path(tmp) / "Python.framework" / "Versions" / "3.14" / "bin" / "python3.14"
            selected_python.parent.mkdir(parents=True)
            selected_python.write_text("#!/bin/sh\n", encoding="utf-8")
            selected_python.chmod(0o755)

            original_run = install_cli.run
            original_pip = install_cli.glyphs_python_pip
            original_selected_python = install_cli.glyphs_selected_python_bin
            original_python_version = install_cli.python_version
            original_verify = install_cli.verify_runtime
            try:
                install_cli.run = lambda cmd: calls.append(cmd)
                install_cli.glyphs_python_pip = lambda glyphs_version="3": self.fail("Glyphs 4 selected Python should be preferred")
                install_cli.glyphs_selected_python_bin = lambda glyphs_version="3": selected_python if glyphs_version == "4" else None
                install_cli.python_version = lambda python: "3.14.0"
                install_cli.verify_runtime = lambda python, target=None: verify_calls.append((python, target)) or True
                install_cli.install_with_glyphs_python(_repo_root() / "requirements.txt", glyphs_version="4")
            finally:
                install_cli.run = original_run
                install_cli.glyphs_python_pip = original_pip
                install_cli.glyphs_selected_python_bin = original_selected_python
                install_cli.python_version = original_python_version
                install_cli.verify_runtime = original_verify
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

        target = (
            Path(tmp)
            / "Library"
            / "Application Support"
            / "Glyphs 4"
            / "Scripts"
            / "site-packages"
        )
        self.assertEqual(calls[0], [str(selected_python), "-m", "pip", "install", "--upgrade", "pip"])
        self.assertEqual(calls[1][:5], [str(selected_python), "-m", "pip", "install", "--upgrade"])
        self.assertIn(str(target), calls[1])
        self.assertEqual(verify_calls, [(selected_python, target)])

    def test_install_with_custom_python_forces_binary_reinstall(self) -> None:
        install_cli = _load_install_cli()
        calls: list[list[str]] = []
        original_run = install_cli.run
        original_verify = install_cli.verify_runtime
        original_python_version = install_cli.python_version
        try:
            install_cli.run = lambda cmd: calls.append(cmd)
            install_cli.verify_runtime = lambda *args, **kwargs: True
            install_cli.python_version = lambda python: "3.12.9"
            install_cli.install_with_custom_python(Path("/tmp/python3.12"), _repo_root() / "requirements.txt")
        finally:
            install_cli.run = original_run
            install_cli.verify_runtime = original_verify
            install_cli.python_version = original_python_version

        self.assertEqual(calls[0], ["/tmp/python3.12", "-m", "pip", "install", "--upgrade", "pip"])
        self.assertEqual(
            calls[1],
            [
                "/tmp/python3.12",
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--force-reinstall",
                "--no-compile",
                "--only-binary=:all:",
                "--user",
                "-r",
                str(_repo_root() / "requirements.txt"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
