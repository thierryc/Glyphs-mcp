"""Smoke tests for the installer script.

These tests avoid touching the real Glyphs user folders by setting HOME to a
temporary directory. They also avoid invoking pip installs; we only validate
sorting logic, CLI validation, and plugin/skill installation behavior.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import plistlib
import shutil
import sys
import tarfile
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock


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

    def test_terminal_installer_notice_keeps_helper_install_app_only(self) -> None:
        install_cli = _load_install_cli()
        with mock.patch.object(install_cli.console, "print") as output:
            install_cli.print_verified_updates_notice()
        text = " ".join(str(call) for call in output.call_args_list)
        self.assertIn("notifications", text)
        self.assertIn("this Python installer does not add that feature", text)
        self.assertIn("use the macOS installer", text)

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
        source = install_cli.runtime_probe_path().read_text(encoding="utf-8")

        self.assertIn('"objc"', source)
        self.assertIn('"Foundation"', source)
        self.assertIn('"AppKit"', source)
        self.assertIn('"pkg_resources"', source)
        self.assertIn('"_cffi_backend"', source)
        self.assertIn('"rpds"', source)

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
                install_cli.install_plugin(
                    mode="copy",
                    sign_executable=False,
                    release_plugin=(
                        _repo_root()
                        / "src"
                        / "glyphs-mcp"
                        / "Glyphs MCP.glyphsPlugin"
                    ),
                )
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

    def test_release_copy_preserves_verified_signature_without_ad_hoc_signing(self) -> None:
        install_cli = _load_install_cli()
        signature = install_cli.PluginSignature(
            cdhash="trusted",
            team_identifier=install_cli.EXPECTED_DEVELOPER_TEAM,
            authority=install_cli.EXPECTED_DEVELOPER_AUTHORITY,
            hardened_runtime=True,
            timestamped=True,
        )

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            release_plugin = Path(tmp) / "release" / "Glyphs MCP.glyphsPlugin"
            shutil.copytree(
                _repo_root()
                / "src"
                / "glyphs-mcp"
                / "Glyphs MCP.glyphsPlugin",
                release_plugin,
            )
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            original_verify = install_cli.verify_trusted_plugin_signature
            original_sign = install_cli.sign_plugin_executable
            verified: list[Path] = []
            try:
                install_cli.verify_trusted_plugin_signature = (
                    lambda bundle: verified.append(bundle) or signature
                )
                install_cli.sign_plugin_executable = (
                    lambda _bundle: self.fail("release copy must not be ad-hoc signed")
                )
                install_cli.install_plugin(
                    mode="copy",
                    release_plugin=release_plugin,
                )
            finally:
                install_cli.verify_trusted_plugin_signature = original_verify
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
            self.assertEqual(len(verified), 3)
            self.assertEqual(verified[0], release_plugin)
            self.assertEqual(verified[-1], dest)
            self.assertEqual(
                (release_plugin / "Contents" / "MacOS" / "plugin").read_bytes(),
                (dest / "Contents" / "MacOS" / "plugin").read_bytes(),
            )

    def test_release_copy_restores_existing_plugin_after_signature_mismatch(self) -> None:
        install_cli = _load_install_cli()
        trusted = install_cli.PluginSignature(
            cdhash="trusted",
            team_identifier=install_cli.EXPECTED_DEVELOPER_TEAM,
            authority=install_cli.EXPECTED_DEVELOPER_AUTHORITY,
            hardened_runtime=True,
            timestamped=True,
        )
        changed = install_cli.PluginSignature(
            cdhash="changed",
            team_identifier=trusted.team_identifier,
            authority=trusted.authority,
            hardened_runtime=True,
            timestamped=True,
        )

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            release_plugin = Path(tmp) / "release" / "Glyphs MCP.glyphsPlugin"
            shutil.copytree(
                _repo_root()
                / "src"
                / "glyphs-mcp"
                / "Glyphs MCP.glyphsPlugin",
                release_plugin,
            )
            dest = (
                Path(tmp)
                / "Library"
                / "Application Support"
                / "Glyphs 4"
                / "Plugins"
                / "Glyphs MCP.glyphsPlugin"
            )
            dest.mkdir(parents=True)
            marker = dest / "marker.txt"
            marker.write_text("existing\n", encoding="utf-8")
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            original_verify = install_cli.verify_trusted_plugin_signature
            try:
                install_cli.verify_trusted_plugin_signature = (
                    lambda bundle: (
                        changed
                        if ".installing-" in bundle.name
                        else trusted
                    )
                )
                with self.assertRaises(SystemExit):
                    install_cli.install_plugin(
                        mode="copy",
                        overwrite_existing=True,
                        release_plugin=release_plugin,
                    )
            finally:
                install_cli.verify_trusted_plugin_signature = original_verify
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertEqual(marker.read_text(encoding="utf-8"), "existing\n")

    def test_copy_mode_resolves_the_exact_checkout_release(self) -> None:
        install_cli = _load_install_cli()
        signature = install_cli.PluginSignature(
            cdhash="trusted",
            team_identifier=install_cli.EXPECTED_DEVELOPER_TEAM,
            authority=install_cli.EXPECTED_DEVELOPER_AUTHORITY,
            hardened_runtime=True,
            timestamped=True,
        )
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            original_resolve = install_cli.resolve_signed_release_plugin
            original_verify = install_cli.verify_trusted_plugin_signature
            versions: list[str] = []
            try:
                install_cli.resolve_signed_release_plugin = lambda version: (
                    versions.append(version)
                    or (
                        _repo_root()
                        / "src"
                        / "glyphs-mcp"
                        / "Glyphs MCP.glyphsPlugin",
                        None,
                    )
                )
                install_cli.verify_trusted_plugin_signature = lambda _bundle: signature
                install_cli.install_plugin(mode="copy")
            finally:
                install_cli.resolve_signed_release_plugin = original_resolve
                install_cli.verify_trusted_plugin_signature = original_verify
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home
            plist_path = (
                _repo_root()
                / "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Info.plist"
            )
            with plist_path.open("rb") as handle:
                expected_version = plistlib.load(handle)["CFBundleShortVersionString"]
            self.assertEqual(versions, [expected_version])

    def test_installer_zip_validation_rejects_path_traversal(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-unsafe-zip.") as tmp:
            archive = Path(tmp) / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr("../escape", "unsafe")
            with self.assertRaisesRegex(RuntimeError, "unsafe path"):
                install_cli._validate_installer_zip_members(archive)

    def test_installer_zip_validation_rejects_escaping_symlink(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-unsafe-link.") as tmp:
            archive = Path(tmp) / "unsafe-link.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                info = zipfile.ZipInfo("GlyphsMCPInstaller.app/escape")
                info.create_system = 3
                info.external_attr = (0o120777 << 16)
                handle.writestr(info, "../../outside")
            with self.assertRaisesRegex(RuntimeError, "escaping symlink"):
                install_cli._validate_installer_zip_members(archive)

    def test_release_checksum_requires_one_valid_sha256(self) -> None:
        install_cli = _load_install_cli()
        digest = "a" * 64
        self.assertEqual(
            install_cli._expected_asset_checksum(
                f"{digest}  installer-app/GlyphsMCPInstaller.zip\n".encode(),
                "GlyphsMCPInstaller.zip",
            ),
            digest,
        )
        with self.assertRaisesRegex(RuntimeError, "duplicate entries"):
            install_cli._expected_asset_checksum(
                (
                    f"{digest}  one/GlyphsMCPInstaller.zip\n"
                    f"{digest}  two/GlyphsMCPInstaller.zip\n"
                ).encode(),
                "GlyphsMCPInstaller.zip",
            )
        with self.assertRaisesRegex(RuntimeError, "invalid SHA-256"):
            install_cli._expected_asset_checksum(
                b"not-a-digest  GlyphsMCPInstaller.zip\n",
                "GlyphsMCPInstaller.zip",
            )
        with self.assertRaisesRegex(RuntimeError, "does not list"):
            install_cli._expected_asset_checksum(
                f"{digest}  ../GlyphsMCPInstaller.zip\n".encode(),
                "GlyphsMCPInstaller.zip",
            )

    def test_trusted_plugin_verification_requires_stapled_notarization_ticket(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-gatekeeper.") as tmp:
            plugin = Path(tmp) / "Glyphs MCP.glyphsPlugin"
            executable = plugin / "Contents" / "MacOS" / "plugin"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"loader")
            (plugin / "Contents" / "CodeResources").write_bytes(b"ticket")
            commands: list[list[str]] = []
            original_run = install_cli._run_signature_command
            try:
                def fake_run(command: list[str], _subject: Path) -> str:
                    commands.append(command)
                    if command[:3] == ["/usr/bin/codesign", "-d", "--verbose=4"]:
                        return (
                            "flags=0x10000(runtime)\n"
                            "CDHash=trusted\n"
                            f"Authority={install_cli.EXPECTED_DEVELOPER_AUTHORITY}\n"
                            "Timestamp=Jul 29, 2026\n"
                            f"TeamIdentifier={install_cli.EXPECTED_DEVELOPER_TEAM}\n"
                        )
                    return ""

                install_cli._run_signature_command = fake_run
                install_cli.verify_trusted_plugin_signature(plugin)
            finally:
                install_cli._run_signature_command = original_run

            self.assertTrue(
                any(command[:3] == ["/usr/bin/xcrun", "stapler", "validate"] for command in commands)
            )

    def test_signed_installer_payload_archive_resolves_plugin(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-payload-archive.") as tmp:
            root = Path(tmp)
            app = root / "GlyphsMCPInstaller.app"
            resources = app / "Contents" / "Resources"
            resources.mkdir(parents=True)
            archive = resources / "Payload.gmcparchive"
            source = root / "source"
            info = (
                source
                / "Payload"
                / "Glyphs MCP.glyphsPlugin"
                / "Contents"
                / "Info.plist"
            )
            info.parent.mkdir(parents=True)
            info.write_bytes(b"plist")
            with tarfile.open(archive, "w:gz") as handle:
                handle.add(source / "Payload", arcname="Payload")
            extraction = root / "extraction"
            extraction.mkdir()

            plugin = install_cli._resolve_installer_payload_plugin(app, extraction)

            self.assertEqual(plugin.name, "Glyphs MCP.glyphsPlugin")
            self.assertTrue((plugin / "Contents" / "Info.plist").is_file())

    def test_signed_payload_archive_rejects_traversal(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-unsafe-payload.") as tmp:
            root = Path(tmp)
            archive_path = root / "Payload.gmcparchive"
            with tarfile.open(archive_path, "w:gz") as archive:
                info = tarfile.TarInfo("../escape")
                payload = b"unsafe"
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            with self.assertRaisesRegex(RuntimeError, "unsafe path"):
                install_cli._extract_signed_payload_archive(
                    archive_path,
                    root / "extract",
                )

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

        def fake_install_custom(
            python: Path,
            req: Path,
            glyphs_version: str = "4",
        ) -> None:
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
            original_check_runtime = install_cli.check_existing_glyphs_runtime
            signed: list[Path] = []
            try:
                install_cli.show_client_guidance = lambda: self.fail("client guidance should not run")
                install_cli.sign_plugin_executable = lambda bundle: signed.append(bundle)
                install_cli.check_existing_glyphs_runtime = lambda glyphs_version="4": None
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
                install_cli.check_existing_glyphs_runtime = original_check_runtime
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
            self.assertEqual(set(installed), set(install_cli.MANAGED_SKILL_NAMES))
            for skill_name in installed:
                self.assertIn(skill_name, install_cli.MANAGED_SKILL_NAMES)
                skill_path = Path(tmp) / ".codex" / "skills" / skill_name
                self.assertTrue((skill_path / "SKILL.md").is_file())
                self.assertTrue(install_cli._is_installer_owned_skill(skill_path, skill_name))
            self.assertTrue(
                (
                    Path(tmp)
                    / ".codex"
                    / "skills"
                    / "glyphs-mcp-development"
                    / "scripts"
                    / "scaffold.py"
                ).is_file()
            )
            scripting_path = Path(tmp) / ".codex" / "skills" / "glyphs-mcp-scripting"
            self.assertTrue((scripting_path / "SKILL.md").is_file())
            self.assertTrue((scripting_path / "agents" / "openai.yaml").is_file())
            self.assertTrue((Path(tmp) / ".codex" / "skills" / "third-party-skill" / "SKILL.md").is_file())

    def test_install_skill_bundle_overwrites_managed_skills_only_when_requested(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                dest_root = install_cli.claude_code_skills_dir()
                managed_dest = dest_root / "glyphs"
                managed_dest.mkdir(parents=True, exist_ok=True)
                (managed_dest / "SKILL.md").write_text("old managed skill\n", encoding="utf-8")
                install_cli._write_skill_ownership_marker(managed_dest, "glyphs")

                legacy_dest = dest_root / "glyphs-mcp-connect"
                legacy_dest.mkdir(parents=True, exist_ok=True)
                (legacy_dest / "SKILL.md").write_text("old connect skill\n", encoding="utf-8")
                install_cli._write_skill_ownership_marker(legacy_dest, "glyphs-mcp-connect")

                unrelated = dest_root / "another-skill"
                unrelated.mkdir(parents=True, exist_ok=True)
                (unrelated / "SKILL.md").write_text("keep me\n", encoding="utf-8")

                installed, skipped = install_cli.install_skill_bundle(dest_root, overwrite_existing=True)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertIn("glyphs", installed)
            self.assertFalse(skipped)
            self.assertIn("name: glyphs", (managed_dest / "SKILL.md").read_text(encoding="utf-8"))
            self.assertFalse(legacy_dest.exists())
            self.assertEqual((unrelated / "SKILL.md").read_text(encoding="utf-8"), "keep me\n")

    def test_install_skill_bundle_preserves_unmarked_same_named_skill(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            dest_root = Path(tmp) / ".codex" / "skills"
            unowned = dest_root / "glyphs"
            unowned.mkdir(parents=True)
            skill_file = unowned / "SKILL.md"
            skill_file.write_text("# unrelated glyphs skill\n", encoding="utf-8")

            installed, skipped = install_cli.install_skill_bundle(
                dest_root,
                overwrite_existing=True,
            )

            self.assertIn("glyphs", skipped)
            self.assertNotIn("glyphs", installed)
            self.assertEqual(
                skill_file.read_text(encoding="utf-8"),
                "# unrelated glyphs skill\n",
            )
            self.assertFalse(
                (unowned / install_cli.SKILL_OWNERSHIP_MARKER).exists()
            )

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
            self.assertTrue((Path(tmp) / ".codex" / "skills" / "glyphs" / "SKILL.md").is_file())
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
            self.assertTrue((Path(tmp) / ".claude" / "skills" / "glyphs" / "SKILL.md").is_file())
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
            self.assertTrue((Path(tmp) / ".codex" / "skills" / "glyphs" / "SKILL.md").is_file())
            self.assertTrue((Path(tmp) / ".claude" / "skills" / "glyphs" / "SKILL.md").is_file())

    def test_install_skill_bundle_for_targets_requires_policy_when_managed_skills_exist(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                managed_dest = install_cli.codex_skills_dir() / "glyphs"
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
                managed_dest = dest_root / "glyphs"
                managed_dest.mkdir(parents=True, exist_ok=True)
                (managed_dest / "SKILL.md").write_text("old managed skill\n", encoding="utf-8")
                install_cli._write_skill_ownership_marker(managed_dest, "glyphs")
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

            self.assertIn("name: glyphs", (managed_dest / "SKILL.md").read_text(encoding="utf-8"))

    def test_existing_managed_skills_are_kept_when_requested(self) -> None:
        install_cli = _load_install_cli()

        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-installer-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                dest_root = install_cli.codex_skills_dir()
                managed_dest = dest_root / "glyphs"
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
                install_cli.install_plugin(
                    mode="copy",
                    overwrite_existing=True,
                    sign_executable=False,
                    release_plugin=(
                        _repo_root()
                        / "src"
                        / "glyphs-mcp"
                        / "Glyphs MCP.glyphsPlugin"
                    ),
                )
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

    def test_install_with_glyphs_python_avoids_forced_reinstall(self) -> None:
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
            original_preflight = install_cli.check_runtime_preinstall
            try:
                install_cli.run = lambda cmd, **kwargs: calls.append(cmd)
                install_cli.glyphs_selected_python_bin = lambda glyphs_version="4": None
                install_cli.glyphs_python_pip = lambda glyphs_version="4": fake_pip
                install_cli.verify_runtime = lambda *args, **kwargs: True
                install_cli.check_runtime_preinstall = lambda *args, **kwargs: None
                install_cli.install_with_glyphs_python(_repo_root() / "requirements.txt")
            finally:
                install_cli.run = original_run
                install_cli.glyphs_python_pip = original_pip
                install_cli.glyphs_selected_python_bin = original_selected_python
                install_cli.verify_runtime = original_verify
                install_cli.check_runtime_preinstall = original_preflight
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
        self.assertEqual(
            calls[0],
            [
                str(fake_pip),
                "install",
                "--upgrade",
                "--upgrade-strategy",
                "only-if-needed",
                "--disable-pip-version-check",
                "--no-input",
                "--progress-bar",
                "off",
                "--timeout",
                "30",
                "--retries",
                "2",
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
            original_preflight = install_cli.check_runtime_preinstall
            try:
                install_cli.run = lambda cmd, **kwargs: calls.append(cmd)
                install_cli.glyphs_python_pip = lambda glyphs_version="3": self.fail("Glyphs 4 selected Python should be preferred")
                install_cli.glyphs_selected_python_bin = lambda glyphs_version="3": selected_python if glyphs_version == "4" else None
                install_cli.python_version = lambda python: "3.14.0"
                install_cli.verify_runtime = lambda python, target=None: verify_calls.append((python, target)) or True
                install_cli.check_runtime_preinstall = lambda *args, **kwargs: None
                install_cli.install_with_glyphs_python(_repo_root() / "requirements.txt", glyphs_version="4")
            finally:
                install_cli.run = original_run
                install_cli.glyphs_python_pip = original_pip
                install_cli.glyphs_selected_python_bin = original_selected_python
                install_cli.python_version = original_python_version
                install_cli.verify_runtime = original_verify
                install_cli.check_runtime_preinstall = original_preflight
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
        self.assertEqual(calls[0][:5], [str(selected_python), "-m", "pip", "install", "--upgrade"])
        self.assertIn(str(target), calls[0])
        self.assertNotIn("--force-reinstall", calls[0])
        self.assertEqual(verify_calls, [(selected_python, target)])

    def test_install_with_custom_python_avoids_forced_reinstall(self) -> None:
        install_cli = _load_install_cli()
        calls: list[list[str]] = []
        original_run = install_cli.run
        original_verify = install_cli.verify_runtime
        original_python_version = install_cli.python_version
        original_preflight = install_cli.check_runtime_preinstall
        try:
            install_cli.run = lambda cmd, **kwargs: calls.append(cmd)
            install_cli.verify_runtime = lambda *args, **kwargs: True
            install_cli.python_version = lambda python: "3.12.9"
            install_cli.check_runtime_preinstall = lambda *args, **kwargs: None
            install_cli.install_with_custom_python(Path("/tmp/python3.12"), _repo_root() / "requirements.txt")
        finally:
            install_cli.run = original_run
            install_cli.verify_runtime = original_verify
            install_cli.python_version = original_python_version
            install_cli.check_runtime_preinstall = original_preflight

        self.assertEqual(
            calls[0],
            [
                "/tmp/python3.12",
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--upgrade-strategy",
                "only-if-needed",
                "--disable-pip-version-check",
                "--no-input",
                "--progress-bar",
                "off",
                "--timeout",
                "30",
                "--retries",
                "2",
                "--no-compile",
                "--only-binary=:all:",
                "--user",
                "-r",
                str(_repo_root() / "requirements.txt"),
            ],
        )

    def test_uninstall_parser_keeps_glyphs_4_default_and_accepts_both(self) -> None:
        install_cli = _load_install_cli()

        default_options = install_cli.parse_cli_options(["--uninstall", "--dry-run"])
        both_options = install_cli.parse_cli_options(["--uninstall", "--dry-run", "--glyphs-version", "both"])

        self.assertEqual(default_options.glyphs_version, "4")
        self.assertEqual(both_options.glyphs_version, "both")
        self.assertTrue(default_options.uninstall)

    def test_glyphs_both_is_rejected_for_install(self) -> None:
        self.assert_parser_error(
            ["--glyphs-version", "both"],
            "--glyphs-version both can only be used with --uninstall.",
        )

    def test_non_interactive_uninstall_requires_explicit_confirmation(self) -> None:
        self.assert_parser_error(
            ["--uninstall", "--non-interactive"],
            "--non-interactive --uninstall requires --confirm-uninstall",
        )

        install_cli = _load_install_cli()
        options = install_cli.parse_cli_options(["--uninstall", "--non-interactive", "--dry-run"])
        self.assertTrue(options.dry_run)

    def test_uninstall_component_flag_is_repeatable(self) -> None:
        install_cli = _load_install_cli()
        options = install_cli.parse_cli_options([
            "--uninstall",
            "--dry-run",
            "--uninstall-component",
            "plugin",
            "--uninstall-component",
            "clients",
        ])
        self.assertEqual(options.uninstall_components, frozenset({"plugin", "clients"}))

    def test_uninstall_rejects_install_only_options(self) -> None:
        self.assert_parser_error(
            ["--uninstall", "--skip-deps"],
            "Install-only options cannot be used with --uninstall.",
        )

    def test_uninstall_plan_targets_both_exact_plugin_paths(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-uninstall-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                plan = install_cli.build_uninstall_plan("both", frozenset({"plugin"}))
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

        self.assertEqual([item.glyphs_version for item in plan.candidates], ["3", "4"])
        self.assertTrue(str(plan.candidates[0].location).endswith("Glyphs 3/Plugins/Glyphs MCP.glyphsPlugin"))
        self.assertTrue(str(plan.candidates[1].location).endswith("Glyphs 4/Plugins/Glyphs MCP.glyphsPlugin"))

    def test_uninstalling_plugin_symlink_never_removes_target(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-uninstall-home.") as tmp, tempfile.TemporaryDirectory(prefix="glyphs-mcp-plugin-source.") as source_tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                source = Path(source_tmp) / "Glyphs MCP.glyphsPlugin"
                source.mkdir()
                marker = source / "keep.txt"
                marker.write_text("keep\n", encoding="utf-8")
                dest = install_cli.glyphs_plugins_dir("4") / source.name
                dest.parent.mkdir(parents=True)
                dest.symlink_to(source, target_is_directory=True)

                plan = install_cli.build_uninstall_plan("4", frozenset({"plugin"}))
                outcomes = install_cli.execute_uninstall_plan(plan)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertEqual(outcomes[0].status, "removed")
            self.assertFalse(dest.exists())
            self.assertTrue(marker.exists())

    def test_uninstaller_removes_only_marker_owned_updater_data(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-uninstall-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                root = install_cli.updater_root()
                root.mkdir(parents=True)
                (root / install_cli.UPDATER_MANAGED_MARKER).write_text(
                    install_cli.UPDATER_MANAGED_MARKER_VALUE,
                    encoding="utf-8",
                )
                (root / "GlyphsMCPUpdater").write_text("fixture", encoding="utf-8")
                (root / "Staged").mkdir()
                plan = install_cli.build_uninstall_plan("4", frozenset({"updater"}))
                outcomes = install_cli.execute_uninstall_plan(plan)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertEqual(len(plan.candidates), 1)
            self.assertEqual(plan.candidates[0].state, "removable")
            self.assertEqual(outcomes[0].status, "removed")
            self.assertFalse(root.exists())

    def test_uninstaller_preserves_unmarked_or_unrecognized_updater_data(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-uninstall-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                root = install_cli.updater_root()
                root.mkdir(parents=True)
                (root / install_cli.UPDATER_MANAGED_MARKER).write_text(
                    install_cli.UPDATER_MANAGED_MARKER_VALUE,
                    encoding="utf-8",
                )
                custom = root / "personal-notes.txt"
                custom.write_text("preserve", encoding="utf-8")
                plan = install_cli.build_uninstall_plan("4", frozenset({"updater"}))
                outcomes = install_cli.execute_uninstall_plan(plan)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertEqual(plan.candidates[0].state, "blocked")
            self.assertEqual(outcomes[0].status, "skipped")
            self.assertTrue(custom.exists())

    def test_uninstaller_removes_only_marker_owned_skills(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-uninstall-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                root = install_cli.codex_skills_dir()
                unowned_same_name = root / "glyphs"
                managed = root / "glyphs-mcp-spacing"
                managed_scripting = root / "glyphs-mcp-scripting"
                custom = root / "glyphs-mcp-private-notes"
                unrelated = root / "another-skill"
                for path in (unowned_same_name, managed, managed_scripting, custom, unrelated):
                    path.mkdir(parents=True, exist_ok=True)
                (unowned_same_name / "SKILL.md").write_text(
                    "# unrelated glyphs skill\n",
                    encoding="utf-8",
                )
                install_cli._write_skill_ownership_marker(
                    managed,
                    "glyphs-mcp-spacing",
                )
                install_cli._write_skill_ownership_marker(
                    managed_scripting,
                    "glyphs-mcp-scripting",
                )
                plan = install_cli.build_uninstall_plan("4", frozenset({"skills"}))
                outcomes = install_cli.execute_uninstall_plan(plan)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertEqual(
                [outcome.candidate.location.name for outcome in outcomes],
                ["glyphs", "glyphs-mcp-scripting", "glyphs-mcp-spacing"],
            )
            self.assertEqual(outcomes[0].status, "skipped")
            self.assertEqual(outcomes[0].candidate.state, "preserved")
            self.assertTrue(unowned_same_name.exists())
            self.assertFalse(managed.exists())
            self.assertFalse(managed_scripting.exists())
            self.assertTrue(custom.exists())
            self.assertTrue(unrelated.exists())

    def test_uninstaller_removes_matching_client_entries_with_backups(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-uninstall-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                codex = install_cli.codex_config_path()
                codex.parent.mkdir(parents=True)
                codex.write_text(
                    "model = \"gpt-5\"\n\n"
                    "[mcp_servers.glyphs-mcp-server]\n"
                    f"url = \"{install_cli.MCP_ENDPOINT}\"\n"
                    "enabled = true\n\n"
                    "[mcp_servers.keep-me]\nurl = \"https://example.test\"\n",
                    encoding="utf-8",
                )
                claude_code = install_cli.claude_code_config_path()
                claude_code.write_text(json.dumps({
                    "theme": "dark",
                    "mcpServers": {
                        "glyphs-mcp": {"type": "http", "url": install_cli.MCP_ENDPOINT},
                        "keep-me": {"type": "http", "url": "https://example.test"},
                    },
                }), encoding="utf-8")
                desktop = install_cli.claude_desktop_config_path()
                desktop.parent.mkdir(parents=True)
                desktop.write_text(json.dumps({
                    "preferences": {"theme": "dark"},
                    "mcpServers": {
                        "glyphs-mcp-server": {"command": "npx", "args": ["mcp-remote", install_cli.MCP_ENDPOINT]},
                    },
                }), encoding="utf-8")

                plan = install_cli.build_uninstall_plan("4", frozenset({"clients"}))
                outcomes = install_cli.execute_uninstall_plan(plan)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertTrue(all(outcome.status == "removed" for outcome in outcomes))
            self.assertNotIn("[mcp_servers.glyphs-mcp-server]", codex.read_text(encoding="utf-8"))
            self.assertIn("[mcp_servers.keep-me]", codex.read_text(encoding="utf-8"))
            self.assertIn("keep-me", json.loads(claude_code.read_text(encoding="utf-8"))["mcpServers"])
            self.assertEqual(json.loads(desktop.read_text(encoding="utf-8"))["preferences"], {"theme": "dark"})
            self.assertTrue(list(codex.parent.glob("config.toml.bak-*")))
            self.assertTrue(list(claude_code.parent.glob(".claude.json.bak-*")))
            self.assertTrue(list(desktop.parent.glob("claude_desktop_config.json.bak-*")))

    def test_same_named_custom_client_entry_is_preserved(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-uninstall-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                path = install_cli.codex_config_path()
                path.parent.mkdir(parents=True)
                original = "[mcp_servers.glyphs-mcp-server]\nurl = \"https://custom.example/mcp\"\n"
                path.write_text(original, encoding="utf-8")
                plan = install_cli.build_uninstall_plan("4", frozenset({"clients"}))
                codex = next(item for item in plan.candidates if item.client_kind == "codex")
                outcomes = install_cli.execute_uninstall_plan(plan)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertEqual(codex.state, "preserved")
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertFalse(any(outcome.candidate.client_kind == "codex" and outcome.status == "removed" for outcome in outcomes))

    def test_uninstall_never_touches_python_dependencies_or_parent_folders(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-uninstall-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                plugin = install_cli.glyphs_plugins_dir("4") / "Glyphs MCP.glyphsPlugin"
                plugin.mkdir(parents=True)
                site_package = install_cli.glyphs_scripts_site_packages("4") / "shared_package" / "__init__.py"
                site_package.parent.mkdir(parents=True)
                site_package.write_text("shared = True\n", encoding="utf-8")
                plugins_parent = plugin.parent
                plan = install_cli.build_uninstall_plan("4", frozenset({"plugin"}))
                install_cli.execute_uninstall_plan(plan)
            finally:
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertTrue(site_package.exists())
            self.assertTrue(plugins_parent.is_dir())

    def test_running_app_detection_fails_closed_when_processes_cannot_be_read(self) -> None:
        install_cli = _load_install_cli()
        original = install_cli.subprocess.check_output
        try:
            install_cli.subprocess.check_output = lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied"))
            self.assertEqual(install_cli._running_glyphs_versions(), frozenset({"unknown"}))
        finally:
            install_cli.subprocess.check_output = original

    def test_interactive_uninstall_decline_changes_nothing(self) -> None:
        install_cli = _load_install_cli()
        with tempfile.TemporaryDirectory(prefix="glyphs-mcp-uninstall-home.") as tmp:
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            original_confirm = install_cli.Confirm.ask
            original_running = install_cli._running_glyphs_versions
            try:
                plugin = install_cli.glyphs_plugins_dir("4") / "Glyphs MCP.glyphsPlugin"
                plugin.mkdir(parents=True)
                install_cli.Confirm.ask = lambda *args, **kwargs: False
                install_cli._running_glyphs_versions = lambda: frozenset()
                options = install_cli.parse_cli_options(["--uninstall", "--uninstall-component", "plugin"])
                with self.assertRaises(SystemExit) as ctx:
                    install_cli.run_uninstall(options)
            finally:
                install_cli.Confirm.ask = original_confirm
                install_cli._running_glyphs_versions = original_running
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            self.assertEqual(ctx.exception.code, 3)
            self.assertTrue(plugin.exists())


if __name__ == "__main__":
    unittest.main()
