"""Security gates for the entirely local macOS release workflow."""

from __future__ import annotations

import importlib.util
import sys
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
import hashlib
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
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
    versions = root / "src/glyphs-mcp-v2/glyphs_mcp_v2/versions.py"
    versions.parent.mkdir(parents=True, exist_ok=True)
    versions.write_text(f'SERVER_VERSION = "{version}"\n', encoding="utf-8")
    pyproject = root / "src/glyphs-mcp-v2/pyproject.toml"
    pyproject.write_text(f'[project]\nname = "glyphs-mcp-v2"\nversion = "{version}"\n', encoding="utf-8")
    project = root / "macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj"
    project.parent.mkdir(parents=True, exist_ok=True)
    project.write_text(
        "MARKETING_VERSION = {0};\nCURRENT_PROJECT_VERSION = 42;\nMARKETING_VERSION = {0};\n".format(version),
        encoding="utf-8",
    )
    app_plist = root / "dist/installer-app/GlyphsMCPInstaller.app/Contents/Info.plist"
    _write_plist(app_plist, version, "42")
    return app_plist


def _candidate_tree(root: Path, version: str = "2.3.4", build: int = 42) -> Path:
    app_plist = _release_tree(root, version)
    project = root / "macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj"
    project.write_text(
        f"MARKETING_VERSION = {version};\nCURRENT_PROJECT_VERSION = {build};\n",
        encoding="utf-8",
    )
    for relative in (
        "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Info.plist",
        "plugin-manager/Glyphs MCP.glyphsPlugin/Contents/Info.plist",
    ):
        _write_plist(root / relative, "1.11.0")
    for relative in (
        "plugins/glyphs-mcp/.codex-plugin/plugin.json",
        "plugins/glyphs-mcp/.claude-plugin/plugin.json",
        "plugins/glyphs-mcp/.cursor-plugin/plugin.json",
        "plugins/glyphs-mcp/.github/plugin/plugin.json",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"name": "glyphs-mcp", "version": version}), encoding="utf-8")
    knowledge = root / "third_party/glyphs-file-format-v4"
    knowledge.mkdir(parents=True)
    schema = knowledge / "glyphs-4.schema.json"
    specification = knowledge / "GlyphsFileFormatv4.md"
    object_wrapper = knowledge / "GlyphsApp-init.py"
    reporter_template = knowledge / "Reporter-plugin.py"
    palette_template = knowledge / "Palette-plugin.py"
    schema.write_text("{}\n", encoding="utf-8")
    specification.write_text("# Fixture\n", encoding="utf-8")
    object_wrapper.write_text("# ObjectWrapper fixture\n", encoding="utf-8")
    reporter_template.write_text("# Reporter fixture\n", encoding="utf-8")
    palette_template.write_text("# Palette fixture\n", encoding="utf-8")
    (knowledge / "LICENSE").write_text("Apache-2.0 fixture\n", encoding="utf-8")
    dependencies = []
    for identity, path in (
        ("glyphs-file-format-v4-schema", schema),
        ("glyphs-file-format-v4-specification", specification),
        ("glyphs-object-wrapper", object_wrapper),
        ("glyphs-python-reporter-template", reporter_template),
        ("glyphs-python-palette-template", palette_template),
    ):
        dependencies.append(
            {
                "id": identity,
                "source": "https://example.invalid/GlyphsSDK",
                "branch": "Glyphs3",
                "commit": "a" * 40,
                "path": path.name,
                "localPath": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "license": "Apache-2.0",
                "role": "fixture",
                "auditedAt": "2026-08-22",
            }
        )
    (knowledge / "knowledge-dependencies.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "auditedAt": "2026-08-22",
                "dependencies": dependencies,
            }
        ),
        encoding="utf-8",
    )
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

    def test_metadata_gate_rejects_v2_source_xcode_and_built_app_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyphs-release-security.") as temp:
            root = Path(temp)
            app_plist = _release_tree(root)

            pyproject = root / "src/glyphs-mcp-v2/pyproject.toml"
            pyproject.write_text(
                '[project]\nname = "glyphs-mcp-v2"\nversion = "2.3.5"\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "pyproject version"):
                self.security.validate_release_metadata(root, "v2.3.4", app_plist)

            pyproject.write_text(
                '[project]\nname = "glyphs-mcp-v2"\nversion = "2.3.4"\n',
                encoding="utf-8",
            )
            project = root / "macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj"
            project.write_text("MARKETING_VERSION = 9.9.9;\nCURRENT_PROJECT_VERSION = 42;\n", encoding="utf-8")
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "MARKETING_VERSION"):
                self.security.validate_release_metadata(root, "v2.3.4", app_plist)

            project.write_text("MARKETING_VERSION = 2.3.4;\nCURRENT_PROJECT_VERSION = 42;\n", encoding="utf-8")
            _write_plist(app_plist, "2.3.5", "42")
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "built installer version"):
                self.security.validate_release_metadata(root, "v2.3.4", app_plist)

    def test_unsigned_candidate_validates_asymmetric_versions_and_explicit_build(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyphs-unsigned-candidate.") as temp:
            root = Path(temp)
            _candidate_tree(root)

            result = self.security.validate_unsigned_candidate(
                root,
                expected_version="2.3.4",
                installer_build=42,
            )

            self.assertEqual(result["releaseVersion"], "2.3.4")
            self.assertEqual(result["installerBuild"], 42)
            self.assertEqual(result["targets"]["3"], "1.11.0")
            self.assertEqual(result["targets"]["4"], "2.3.4")
            self.assertEqual(result["canonicalSchemaVersion"], 8)
            self.assertEqual(result["publicToolCount"], 20)
            self.assertEqual(result["managedSkillCount"], 18)
            self.assertIsNone(result["runtimeIdentity"])
            self.assertEqual(len(result["knowledgeDependencies"]["verified"]), 5)

            pinned = root / "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Info.plist"
            _write_plist(pinned, "2.3.4")
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "pinned Glyphs 3"):
                self.security.validate_unsigned_candidate(
                    root,
                    expected_version="2.3.4",
                    installer_build=42,
                )

            _write_plist(pinned, "1.11.0")
            with self.assertRaisesRegex(self.security.ReleaseSecurityError, "installer build"):
                self.security.validate_unsigned_candidate(
                    root,
                    expected_version="2.3.4",
                    installer_build=43,
                )

    def test_knowledge_gate_fails_closed_on_vendored_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyphs-knowledge-security.") as temp:
            root = Path(temp)
            _candidate_tree(root)
            result = self.security.validate_knowledge_dependencies(root)
            self.assertEqual(len(result["verified"]), 5)

            schema = root / "third_party/glyphs-file-format-v4/glyphs-4.schema.json"
            schema.write_text("{\"drift\": true}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                self.security.ReleaseSecurityError, "hash differs"
            ):
                self.security.validate_knowledge_dependencies(root)

    def test_knowledge_gate_rejects_incomplete_authoritative_provenance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="glyphs-knowledge-provenance.") as temp:
            root = Path(temp)
            _candidate_tree(root)
            manifest_path = root / "third_party/glyphs-file-format-v4/knowledge-dependencies.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["dependencies"][0].pop("path")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(
                self.security.ReleaseSecurityError, "lacks path"
            ):
                self.security.validate_knowledge_dependencies(root)

    def test_local_gate_composes_payload_skills_docs_and_unsigned_candidate_checks(self) -> None:
        runner = (REPO / "scripts/run_local_release_tests.sh").read_text(encoding="utf-8")
        for required in (
            "bump_version.py",
            "--dry-run",
            "build_installer_payload.py",
            "diff -qr",
            "sync_codex_plugin_skills.sh --check",
            "check_lean_package.py",
            "npm run build",
            "release_security.py candidate",
            'export PYTHON_BIN="$python_bin"',
        ):
            self.assertIn(required, runner)
        project = (
            REPO
            / "macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj"
        ).read_text(encoding="utf-8")
        self.assertIn('${CODE_SIGNING_ALLOWED:-YES}', project)
        self.assertIn("leaving payload plug-in executables unsigned", project)

    def test_candidate_repository_uses_the_canonical_beta_branch(self) -> None:
        completed = mock.Mock(returncode=0, stderr="")
        with (
            mock.patch.object(
                self.security,
                "release_identity",
                return_value={"channel": "beta"},
            ),
            mock.patch.object(
                self.security.subprocess,
                "run",
                return_value=completed,
            ) as run,
        ):
            self.security.validate_candidate_repository_state(REPO)

        self.assertEqual(run.call_count, 1)
        self.assertEqual(
            run.call_args.args[0],
            ["git", "merge-base", "--is-ancestor", "origin/lit/v2-beta", "HEAD"],
        )

    def test_candidate_repository_keeps_stable_main_ancestry_checks(self) -> None:
        completed = mock.Mock(returncode=0, stderr="")
        with (
            mock.patch.object(
                self.security,
                "release_identity",
                return_value={"channel": "stable"},
            ),
            mock.patch.object(
                self.security.subprocess,
                "run",
                return_value=completed,
            ) as run,
        ):
            self.security.validate_candidate_repository_state(REPO)

        self.assertEqual(
            [call.args[0][3] for call in run.call_args_list],
            ["main", "origin/main"],
        )

    def test_candidate_repository_fails_closed_when_beta_base_is_missing(self) -> None:
        completed = mock.Mock(returncode=1, stderr="fatal: bad revision")
        with (
            mock.patch.object(
                self.security,
                "release_identity",
                return_value={"channel": "beta"},
            ),
            mock.patch.object(
                self.security.subprocess,
                "run",
                return_value=completed,
            ),
        ):
            with self.assertRaisesRegex(
                self.security.ReleaseSecurityError,
                "origin/lit/v2-beta.*fatal: bad revision",
            ):
                self.security.validate_candidate_repository_state(REPO)

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
            "run_python_tests.sh",
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
        expected = ["Glyphs-MCP-2.3.4.dmg", "SHA256SUMS"]
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
                "must be empty",
            ),
            (
                {
                    "tagName": "v2.3.4",
                    "isDraft": True,
                    "assets": [{"name": "unrelated-notes.txt"}],
                },
                "must be empty",
            ),
        ]
        for state, message in invalid_states:
            with self.subTest(state=state):
                with self.assertRaisesRegex(self.security.ReleaseSecurityError, message):
                    self.security.validate_release_state(state, "v2.3.4", expected)

    def test_publisher_has_local_fail_closed_gates_and_no_release_action(self) -> None:
        publish = (REPO / "scripts" / "publish_release_assets.sh").read_text(encoding="utf-8")
        build = (REPO / "scripts" / "build_installer_app.sh").read_text(encoding="utf-8")
        verify = (REPO / "scripts" / "verify_release_artifacts.sh").read_text(encoding="utf-8")
        notarize = (REPO / "scripts" / "notarize_installer_app.sh").read_text(encoding="utf-8")

        self.assertIn("git status --porcelain", publish)
        self.assertIn("git verify-tag", publish)
        self.assertIn("git fetch --quiet origin", publish)
        self.assertIn("git ls-remote origin", publish)
        self.assertIn(
            "GLYPHS_MCP_FULL_NETWORK=1 ./scripts/run_local_release_tests.sh",
            publish,
        )
        self.assertIn("--confirm-publish", publish)
        self.assertIn("verify_release_artifacts.sh", publish)
        self.assertIn("run_local_release_tests.sh", publish)
        self.assertIn("SHA256SUMS", publish)
        self.assertNotIn("--clobber", publish)
        self.assertIn("release-state", publish)
        self.assertIn(
            'gh release view "$tag" --json tagName,isDraft,isPrerelease,url,assets',
            publish,
        )
        self.assertIn("sign_nested_payload_code", build)
        self.assertIn('release_payload.py" sign', build)
        self.assertIn('ARCHS="arm64 x86_64"', build)
        self.assertIn('release_payload.py" verify', verify)
        self.assertIn('--installed', verify)
        self.assertIn('GlyphsMCPNotaryPayload.zip', notarize)
        self.assertIn('release_payload.py" refresh', notarize)
        self.assertIn('release_payload.py" bundles', notarize)
        self.assertIn('gh release edit "$tag" --draft=false --prerelease=false --latest', publish)
        self.assertIn('releases/latest', publish)
        self.assertLess(publish.index('release_discovery.py'), publish.index('gh release edit'))
        self.assertIn("--remove-signature", build)
        self.assertNotIn("codesign --force --sign", build)
        self.assertIn("--deep --strict", build)
        self.assertIn("--timestamp --options runtime", build)
        self.assertIn("Payload.gmcparchive", build)
        self.assertIn("/usr/bin/tar -czf", build)
        self.assertIn("/usr/bin/env -u COPYFILE_DISABLE /usr/bin/tar -czf", build)
        self.assertNotIn("COPYFILE_DISABLE=1", build + notarize)
        self.assertIn("payload_archive_sha256_before_signing", build)
        self.assertIn("payload_archive_sha256_after_signing", build)
        self.assertIn("GlyphsMCPUpdater", build)
        self.assertIn("updater helper is missing hardened runtime", build)
        self.assertIn("sleep 15", build)
        self.assertGreaterEqual(build.count("/usr/bin/tar -xzf"), 2)
        self.assertIn("Authority=$expected_identity", verify)
        self.assertIn("TeamIdentifier=$expected_team", verify)
        self.assertIn("stapler validate", verify)
        self.assertIn("spctl_bin", verify)
        self.assertIn("verify_checksum_args", verify)
        self.assertIn('checksum_stage="$tmp_root/release-assets"', verify)
        self.assertIn('staged_artifact="$checksum_stage/$(basename "$artifact")"', verify)
        self.assertIn('--base-dir "$checksum_stage"', verify)
        self.assertIn("verify_payload_executables", verify)
        self.assertIn("zipped_payload_root", verify)
        self.assertIn("zipped_core_framework", verify)
        self.assertIn("zipped_updater_helper", verify)
        self.assertIn('verify_runtime_signature "$updater_helper" 0', verify)
        self.assertIn('--verify-root "$zipped_payload_root"', verify)
        self.assertIn('--release-version "$version"', verify)
        self.assertNotIn("include-plugin-zip", publish)
        self.assertNotIn("Glyphs MCP.glyphsPlugin-v$version.zip", publish)
        self.assertIn("Payload.gmcparchive", notarize)
        self.assertEqual(notarize.count("notarytool submit"), 2)
        self.assertIn('stapler staple "$plugin"', notarize)
        self.assertIn('stapler validate "$plugin"', notarize)
        self.assertIn("stapled_payload_archive", notarize)
        self.assertIn('codesign --sign "$identity" --timestamp --options runtime "$app"', notarize)
        self.assertLess(notarize.index("stapler staple"), notarize.rindex("ditto -c -k --keepParent"))

        release_workflows = []
        for path in (REPO / ".github" / "workflows").glob("*.y*ml"):
            text = path.read_text(encoding="utf-8")
            if "publish_release_assets.sh" in text or "notarytool" in text or "Developer ID Application" in text:
                release_workflows.append(path.name)
        self.assertEqual(release_workflows, [], "Release publishing must remain local-only")

    def test_release_assets_use_the_milestone_13_draft_names(self) -> None:
        publish = (REPO / "scripts" / "publish_release_assets.sh").read_text(
            encoding="utf-8"
        )
        make_dmg = (REPO / "scripts" / "make_installer_dmg.sh").read_text(
            encoding="utf-8"
        )
        verify = (REPO / "scripts" / "verify_release_artifacts.sh").read_text(
            encoding="utf-8"
        )
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        installation = (REPO / "content/getting-started/installation.mdx").read_text(
            encoding="utf-8"
        )

        for script in (publish, make_dmg, verify):
            self.assertRegex(script, r"Glyphs-MCP-\$(?:version|release_version)\.dmg")
            self.assertIn("Glyphs-MCP-latest.dmg", script)
            self.assertNotIn("GlyphsMCPInstaller-$version.dmg", script)
        self.assertIn("Glyphs-MCP-latest.dmg", readme)
        self.assertIn("Choose **Install All** on Setup", installation)
        self.assertIn("**Queued**, **Installing** and **Installed**", installation)
        self.assertNotIn("Choose → Install → Ready", installation)


if __name__ == "__main__":
    unittest.main()
