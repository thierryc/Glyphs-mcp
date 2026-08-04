from __future__ import annotations

import importlib
import json
import os
import plistlib
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
RESOURCES = (
    ROOT
    / "src"
    / "glyphs-mcp"
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)
if str(RESOURCES) not in sys.path:
    sys.path.insert(0, str(RESOURCES))

update_helper = importlib.import_module("update_helper")


class UpdateHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.helper = Path(update_helper.helper_path(str(self.home)))
        self.helper.parent.mkdir(parents=True)
        self.helper.write_bytes(b"fixture helper")
        self.helper.chmod(0o700)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self, *, team: str = update_helper.EXPECTED_TEAM_ID, **overrides):
        calls: list[list[str]] = []
        authority = overrides.get("authority", update_helper.EXPECTED_AUTHORITY)
        runtime = overrides.get("runtime", True)
        timestamp = overrides.get("timestamp", True)
        probe = overrides.get(
            "probe",
            {
                "protocolVersion": 1,
                "helperVersion": "1.0.0",
                "teamIdentifier": update_helper.EXPECTED_TEAM_ID,
                "capabilities": ["prepare"],
                "build": "release",
            },
        )

        def run(arguments, **kwargs):
            del kwargs
            calls.append(list(arguments))
            if arguments[0] == "/usr/bin/codesign" and "-d" in arguments:
                lines = [
                    "TeamIdentifier={}".format(team),
                    "Authority={}".format(authority),
                    "CDHash=abc123",
                    "flags=0x10000{}".format("(runtime)" if runtime else ""),
                ]
                if timestamp:
                    lines.append("Timestamp=Jul 30, 2026")
                output = "\n".join(lines)
            elif arguments[-2:] == ["probe", "--json"]:
                output = json.dumps(probe)
            else:
                output = ""
            return subprocess.CompletedProcess(arguments, 0, stdout=output)

        return run, calls

    def test_paths_are_fixed_under_application_support(self) -> None:
        root = Path(update_helper.updater_root(str(self.home)))
        self.assertEqual(
            root,
            self.home / "Library/Application Support/Glyphs MCP/Updater",
        )
        self.assertEqual(Path(update_helper.helper_path(str(self.home))).parent, root)

    def test_strict_version_target_and_uuid_validation(self) -> None:
        request_id = str(uuid.uuid4())
        self.assertEqual(update_helper.validate_version("1.6.0"), "1.6.0")
        self.assertEqual(update_helper.validate_glyphs_major("3"), 3)
        self.assertEqual(update_helper.normalize_request_id(request_id), request_id)
        for value in ("v1.6.0", "1.6", "01.6.0", "1.6.0-beta", "../1.6.0"):
            with self.subTest(value=value), self.assertRaises(
                update_helper.UpdateHelperError
            ):
                update_helper.validate_version(value)
        for value in (2, 5, "four"):
            with self.subTest(value=value), self.assertRaises(
                update_helper.UpdateHelperError
            ):
                update_helper.validate_glyphs_major(value)

    def test_prepare_arguments_have_no_destination_or_endpoint(self) -> None:
        request_id = str(uuid.uuid4())
        arguments = update_helper.prepare_arguments(
            "1.6.0",
            4,
            request_id,
            home=str(self.home),
        )
        self.assertEqual(
            arguments,
            [
                str(self.helper),
                "prepare",
                "--protocol",
                "1",
                "--version",
                "1.6.0",
                "--glyphs-major",
                "4",
                "--request-id",
                request_id,
            ],
        )
        self.assertNotIn("destination", " ".join(arguments).lower())
        self.assertNotIn("api", " ".join(arguments).lower())

    def test_helper_verification_checks_signature_and_probe(self) -> None:
        run, calls = self._run()
        probe = update_helper.verify_installed_helper(
            path=str(self.helper),
            run=run,
            home=str(self.home),
        )
        self.assertEqual(probe.team_identifier, update_helper.EXPECTED_TEAM_ID)
        self.assertEqual(probe.helper_version, "1.0.0")
        self.assertEqual(calls[-1], [str(self.helper), "probe", "--json"])

    def test_helper_verification_rejects_wrong_team(self) -> None:
        run, _calls = self._run(team="ATTACKER")
        with self.assertRaisesRegex(
            update_helper.UpdateHelperError, "developer team"
        ):
            update_helper.verify_installed_helper(
                path=str(self.helper),
                run=run,
                home=str(self.home),
            )

    def test_helper_verification_rejects_missing_runtime_or_timestamp(self) -> None:
        for overrides, expected in (
            ({"runtime": False}, "hardened runtime"),
            ({"timestamp": False}, "timestamp"),
        ):
            with self.subTest(overrides=overrides):
                run, _calls = self._run(**overrides)
                with self.assertRaisesRegex(update_helper.UpdateHelperError, expected):
                    update_helper.verify_installed_helper(
                        path=str(self.helper),
                        run=run,
                        home=str(self.home),
                    )

    def test_development_signature_requires_explicit_test_mode(self) -> None:
        run, _calls = self._run(authority="Apple Development: Fixture")
        with self.assertRaises(update_helper.UpdateHelperError):
            update_helper.verify_installed_helper(
                path=str(self.helper),
                run=run,
                home=str(self.home),
            )
        probe = update_helper.verify_installed_helper(
            path=str(self.helper),
            run=run,
            allow_development_signature=True,
            home=str(self.home),
        )
        self.assertEqual(probe.build, "release")

    def test_helper_verification_rejects_symlink_and_unsafe_permissions(self) -> None:
        real = self.helper.with_name("real")
        self.helper.rename(real)
        self.helper.symlink_to(real)
        run, _calls = self._run()
        with self.assertRaises(update_helper.UpdateHelperError):
            update_helper.verify_installed_helper(
                path=str(self.helper),
                run=run,
                home=str(self.home),
            )
        self.helper.unlink()
        real.rename(self.helper)
        self.helper.chmod(stat.S_IRWXU | stat.S_IWGRP)
        with self.assertRaisesRegex(update_helper.UpdateHelperError, "permissions"):
            update_helper.verify_installed_helper(
                path=str(self.helper),
                run=run,
                home=str(self.home),
            )

    def test_start_prepare_uses_exact_argv_without_shell(self) -> None:
        captured = {}

        def popen(arguments, **kwargs):
            captured["arguments"] = arguments
            captured["kwargs"] = kwargs
            return mock.Mock()

        request_id = str(uuid.uuid4())
        update_helper.start_prepare(
            "1.6.0",
            3,
            request_id,
            popen=popen,
            home=str(self.home),
        )
        self.assertEqual(captured["arguments"][1], "prepare")
        self.assertNotIn("shell", captured["kwargs"])
        self.assertEqual(captured["kwargs"]["stdin"], subprocess.DEVNULL)

    def test_cancel_only_signals_a_running_owned_process(self) -> None:
        running = mock.Mock()
        running.poll.return_value = None
        self.assertTrue(update_helper.cancel_prepare(running))
        running.send_signal.assert_called_once()
        finished = mock.Mock()
        finished.poll.return_value = 0
        self.assertFalse(update_helper.cancel_prepare(finished))
        finished.send_signal.assert_not_called()

    def test_request_status_must_match_exact_authorization(self) -> None:
        request_id = str(uuid.uuid4())
        path = Path(
            update_helper.request_status_path(request_id, home=str(self.home))
        )
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "protocolVersion": 1,
                    "requestID": request_id,
                    "version": "1.6.0",
                    "glyphsMajor": 4,
                    "phase": "downloading",
                }
            ),
            encoding="utf-8",
        )
        status = update_helper.read_request_status(
            request_id,
            "1.6.0",
            4,
            home=str(self.home),
        )
        self.assertEqual(status["phase"], "downloading")
        with self.assertRaises(update_helper.UpdateHelperError):
            update_helper.read_request_status(
                request_id,
                "1.6.1",
                4,
                home=str(self.home),
            )

    def test_status_reader_rejects_oversized_or_symlinked_files(self) -> None:
        request_id = str(uuid.uuid4())
        path = Path(
            update_helper.request_status_path(request_id, home=str(self.home))
        )
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x" * 65537)
        with self.assertRaisesRegex(update_helper.UpdateHelperError, "too large"):
            update_helper.read_request_status(
                request_id,
                "1.6.0",
                4,
                home=str(self.home),
            )
        path.unlink()
        target = path.with_suffix(".target")
        target.write_text("{}", encoding="utf-8")
        path.symlink_to(target)
        self.assertIsNone(
            update_helper.read_request_status(
                request_id,
                "1.6.0",
                4,
                home=str(self.home),
            )
        )

    def test_ready_stage_requires_matching_per_target_authorization(self) -> None:
        authorization = Path(
            update_helper.authorization_path("1.6.0", 4, home=str(self.home))
        )
        receipt = Path(update_helper.stage_receipt_path("1.6.0", home=str(self.home)))
        plugin = Path(update_helper.staged_plugin_path("1.6.0", home=str(self.home)))
        authorization.parent.mkdir(parents=True)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        executable = plugin / "Contents" / "MacOS" / "plugin"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"signed staged plug-in")
        info = plugin / "Contents" / "Info.plist"
        with info.open("wb") as stream:
            plistlib.dump(
                {
                    "CFBundleIdentifier": "cx.ap.GlyphsMCP",
                    "CFBundleShortVersionString": "1.6.0",
                },
                stream,
            )
        request_id = str(uuid.uuid4())
        authorization.write_text(
            json.dumps(
                {
                    "protocolVersion": 1,
                    "requestID": request_id,
                    "version": "1.6.0",
                    "glyphsMajor": 4,
                }
            ),
            encoding="utf-8",
        )
        receipt.write_text(
            json.dumps(
                {
                    "protocolVersion": 1,
                    "version": "1.6.0",
                    "tag": "v1.6.0",
                    "assetName": "GlyphsMCPInstaller.zip",
                    "assetSHA256": "a" * 64,
                    "teamIdentifier": update_helper.EXPECTED_TEAM_ID,
                    "pluginCDHash": "abc123",
                    "helperVersion": "1.0.0",
                }
            ),
            encoding="utf-8",
        )
        run, _calls = self._run()
        self.assertTrue(
            update_helper.verified_stage_is_ready(
                "1.6.0",
                4,
                home=str(self.home),
                run=run,
            )
        )
        self.assertFalse(
            update_helper.verified_stage_is_ready(
                "1.6.0",
                3,
                home=str(self.home),
                run=run,
            )
        )
        tampered = json.loads(receipt.read_text(encoding="utf-8"))
        tampered["pluginCDHash"] = "different"
        receipt.write_text(json.dumps(tampered), encoding="utf-8")
        self.assertFalse(
            update_helper.verified_stage_is_ready(
                "1.6.0",
                4,
                home=str(self.home),
                run=run,
            )
        )

    def test_plugin_detection_path_does_not_prepare_without_button_action(self) -> None:
        source = (RESOURCES / "glyphs_plugin.py").read_text(encoding="utf-8")
        start_method = source.split("    def start(self):", 1)[1].split(
            "    @objc.python_method", 1
        )[0]
        update_finish = source.split(
            "    def _finish_update_check(", 1
        )[1].split("    @objc.python_method", 1)[0]
        self.assertNotIn("start_prepare(", start_method)
        self.assertNotIn("start_prepare(", update_finish)
        self.assertIn("def UpdateAction_", source)


if __name__ == "__main__":
    unittest.main()
