"""Security gates for the entirely local macOS release workflow."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
SECURITY_MODULE = REPO / "scripts" / "release_security.py"


def _load_security_module():
    spec = importlib.util.spec_from_file_location("glyphs_mcp_release_security", SECURITY_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load release_security.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_plist(path: Path, version: str, build: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(
            {
                "CFBundleShortVersionString": version,
                "CFBundleVersion": build if build is not None else version,
            },
            handle,
        )


def _release_tree(root: Path, version: str = "2.3.4") -> Path:
    _write_plist(root / "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Info.plist", version)
    _write_plist(root / "plugin-manager/Glyphs MCP.glyphsPlugin/Contents/Info.plist", version)
    project = root / "macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj"
    project.parent.mkdir(parents=True, exist_ok=True)
    project.write_text(
        "MARKETING_VERSION = {0};\nCURRENT_PROJECT_VERSION = 42;\nMARKETING_VERSION = {0};\n".format(version),
        encoding="utf-8",
    )
    app_plist = root / "dist/installer-app/GlyphsMCPInstaller.app/Contents/Info.plist"
    _write_plist(app_plist, version, "42")
    return app_plist


class ReleaseSecurityWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.security = _load_security_module()

    def test_metadata_gate_requires_exact_tag_and_aligned_source_installer_versions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyphs-release-security.") as temp:
            root = Path(temp)
            app_plist = _release_tree(root)

            version = self.security.validate_release_metadata(root, "v2.3.4", app_plist)

            self.assertEqual(version, "2.3.4")
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "must exactly match"):
                self.security.validate_release_metadata(root, "v2.3.5", app_plist)

    def test_metadata_gate_rejects_plugin_manager_xcode_and_built_app_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyphs-release-security.") as temp:
            root = Path(temp)
            app_plist = _release_tree(root)

            _write_plist(root / "plugin-manager/Glyphs MCP.glyphsPlugin/Contents/Info.plist", "2.3.5")
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "Plugin Manager version"):
                self.security.validate_release_metadata(root, "v2.3.4", app_plist)

            _write_plist(root / "plugin-manager/Glyphs MCP.glyphsPlugin/Contents/Info.plist", "2.3.4")
            project = root / "macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj"
            project.write_text("MARKETING_VERSION = 9.9.9;\nCURRENT_PROJECT_VERSION = 42;\n", encoding="utf-8")
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "MARKETING_VERSION"):
                self.security.validate_release_metadata(root, "v2.3.4", app_plist)

            project.write_text("MARKETING_VERSION = 2.3.4;\nCURRENT_PROJECT_VERSION = 42;\n", encoding="utf-8")
            _write_plist(app_plist, "2.3.5", "42")
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "built installer version"):
                self.security.validate_release_metadata(root, "v2.3.4", app_plist)

    def test_checksum_manifest_is_deterministic_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyphs-release-checksums.") as temp:
            root = Path(temp)
            first = root / "b.dmg"
            second = root / "installer-app" / "a.zip"
            second.parent.mkdir()
            first.write_bytes(b"dmg")
            second.write_bytes(b"zip")
            manifest = root / "SHA256SUMS"

            self.security.write_checksums([first, second], manifest, root)
            original = manifest.read_text(encoding="utf-8")
            self.security.write_checksums([second, first], manifest, root)
            self.assertEqual(manifest.read_text(encoding="utf-8"), original)
            self.security.verify_checksums(manifest, root)

            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "artifact set differs"):
                self.security.verify_checksums(manifest, root, [first])

            second.write_bytes(b"tampered")
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "checksum mismatch"):
                self.security.verify_checksums(manifest, root)

    def test_checksum_gate_rejects_symlinks_and_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyphs-release-checksums.") as temp:
            root = Path(temp)
            target = root / "real.dmg"
            target.write_bytes(b"real")
            link = root / "linked.dmg"
            link.symlink_to(target)
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "non-symlink"):
                self.security.write_checksums([link], root / "SHA256SUMS", root)

            manifest = root / "SHA256SUMS"
            manifest.symlink_to(target)
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "non-symlink"):
                self.security.verify_checksums(manifest, root)
            manifest.unlink()

            manifest.write_text("0" * 64 + "  ../outside.dmg\n", encoding="utf-8")
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "unsafe"):
                self.security.verify_checksums(manifest, root)

            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "overwrite"):
                self.security.write_checksums([target], target, root)

    def test_release_shell_scripts_parse_and_fail_closed_for_debug_or_skipped_notarization(self) -> None:
        scripts = [
            "build_installer_app.sh",
            "notarize_installer_app.sh",
            "make_installer_dmg.sh",
            "publish_release_assets.sh",
            "run_local_release_tests.sh",
            "verify_release_artifacts.sh",
        ]
        parsed = subprocess.run(
            ["/bin/bash", "-n", *[str(REPO / "scripts" / name) for name in scripts]],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(parsed.returncode, 0, parsed.stderr)

        debug = subprocess.run(
            [str(REPO / "scripts" / "build_installer_app.sh")],
            cwd=REPO,
            env=dict(os.environ, CONFIGURATION="Debug"),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(debug.returncode, 0)
        self.assertIn("only creates distributable Release builds", debug.stderr)

        skipped = subprocess.run(
            [str(REPO / "scripts" / "publish_release_assets.sh"), "--tag", "v1.2.24", "--dry-run"],
            cwd=REPO,
            env=dict(os.environ, SKIP_NOTARIZATION="1"),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(skipped.returncode, 0)
        self.assertIn("publishing is disabled", skipped.stderr)

    def test_release_state_requires_matching_empty_draft(self) -> None:
        expected = ["GlyphsMCPInstaller-2.3.4.dmg", "SHA256SUMS"]
        self.security.validate_release_state(
            {"tagName": "v2.3.4", "isDraft": True, "assets": []},
            "v2.3.4",
            expected,
        )

        invalid_states = [
            ({"tagName": "v9.9.9", "isDraft": True, "assets": []}, "tag mismatch"),
            ({"tagName": "v2.3.4", "isDraft": False, "assets": []}, "must remain a draft"),
            ({"tagName": "v2.3.4", "isDraft": True, "assets": {}}, "malformed"),
            (
                {
                    "tagName": "v2.3.4",
                    "isDraft": True,
                    "assets": [{"name": "SHA256SUMS"}],
                },
                "already contains",
            ),
        ]
        for state, message in invalid_states:
            with self.subTest(state=state):
                with self.assertRaisesRegex(self.security.ReleaseSecurityError, message):
                    self.security.validate_release_state(state, "v2.3.4", expected)

    def test_publisher_has_local_fail_closed_gates_and_no_release_action(self) -> None:
        publish = (REPO / "scripts" / "publish_release_assets.sh").read_text(encoding="utf-8")
        verify = (REPO / "scripts" / "verify_release_artifacts.sh").read_text(encoding="utf-8")
        notarize = (REPO / "scripts" / "notarize_installer_app.sh").read_text(encoding="utf-8")

        self.assertIn("git status --porcelain", publish)
        self.assertIn("git verify-tag", publish)
        self.assertIn("git fetch --quiet origin", publish)
        self.assertIn("git ls-remote origin", publish)
        self.assertIn("--confirm-publish", publish)
        self.assertIn("verify_release_artifacts.sh", publish)
        self.assertIn("run_local_release_tests.sh", publish)
        self.assertIn("SHA256SUMS", publish)
        self.assertNotIn("--clobber", publish)
        self.assertIn("release-state", publish)
        self.assertIn("Authority=$expected_identity", verify)
        self.assertIn("TeamIdentifier=$expected_team", verify)
        self.assertIn("stapler validate", verify)
        self.assertIn("spctl_bin", verify)
        self.assertIn("verify_checksum_args", verify)
        self.assertIn("zipped_payload_bin", verify)
        self.assertIn("zipped_core_framework", verify)
        self.assertLess(notarize.index("stapler staple"), notarize.rindex("ditto -c -k --keepParent"))

        release_workflows = []
        for path in (REPO / ".github" / "workflows").glob("*.y*ml"):
            text = path.read_text(encoding="utf-8")
            if "publish_release_assets.sh" in text or "notarytool" in text or "Developer ID Application" in text:
                release_workflows.append(path.name)
        self.assertEqual(release_workflows, [], "Release publishing must remain local-only")


if __name__ == "__main__":
    unittest.main()
