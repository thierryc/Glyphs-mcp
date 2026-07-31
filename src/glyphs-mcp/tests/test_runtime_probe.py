import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[3]
PROBE_PATH = (
    REPO_ROOT
    / "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Resources/runtime_probe.py"
)
INSTALLER_PATH = REPO_ROOT / "src/glyphs-mcp/scripts/install_cli.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


probe = load_module("glyphs_mcp_runtime_probe_tests", PROBE_PATH)
installer = load_module("glyphs_mcp_install_cli_probe_tests", INSTALLER_PATH)


class RuntimeProbeTests(unittest.TestCase):
    def test_issue_47_cpython_311_file_is_incompatible_with_python_314(self):
        compatible, detected = probe._is_abi_compatible(
            Path("_pydantic_core.cpython-311-darwin.so"),
            "314",
        )
        self.assertFalse(compatible)
        self.assertEqual(detected, "cpython-311")

    def test_cpython_314_abi3_and_universal_binaries_are_compatible(self):
        self.assertTrue(
            probe._is_abi_compatible(
                Path("_pydantic_core.cpython-314-darwin.so"), "314"
            )[0]
        )
        self.assertTrue(
            probe._is_abi_compatible(Path("_pydantic_core.abi3.so"), "314")[0]
        )
        self.assertTrue(
            probe._is_architecture_compatible(["arm64", "x86_64"], "arm64")
        )

    def test_missing_and_pure_python_modules_are_nonblocking_preinstall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fixture_pure.py").write_text("VALUE = 1\n", encoding="utf-8")
            result = probe.run_probe(
                mode="preinstall",
                site_packages=root,
                modules=["fixture_pure", "fixture_missing"],
            )
        self.assertFalse(result["blocking"])
        self.assertEqual(result["status"], "incomplete")
        self.assertTrue(
            any(issue["code"] == "missing_module" for issue in result["issues"])
        )

    def test_python_warnings_are_json_diagnostics_not_raw_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fixture_warning.py").write_text(
                "import warnings\nwarnings.warn('fixture warning', DeprecationWarning)\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROBE_PATH),
                    "--mode",
                    "preinstall",
                    "--site-packages",
                    str(root),
                    "--module",
                    "fixture_warning",
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        payload = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        self.assertEqual(
            payload["checks"][0]["warnings"],
            ["DeprecationWarning: fixture warning"],
        )

    def test_external_fallback_does_not_hide_stale_target_native_file(self):
        current = probe._expected_cpython_tag()
        stale = "311" if current != "311" else "314"
        module = "fixture_native_fallback"
        with tempfile.TemporaryDirectory() as target_directory, tempfile.TemporaryDirectory() as fallback_directory:
            target = Path(target_directory)
            fallback = Path(fallback_directory)
            stale_file = target / f"{module}.cpython-{stale}-darwin.so"
            stale_file.touch()
            (fallback / f"{module}.py").write_text("VALUE = 1\n", encoding="utf-8")
            sys.path.append(str(fallback))
            try:
                with mock.patch.object(
                    probe, "NATIVE_MODULES", probe.NATIVE_MODULES | {module}
                ):
                    result = probe.run_probe(
                        mode="preinstall",
                        site_packages=target,
                        modules=[module],
                    )
            finally:
                sys.path.remove(str(fallback))
                probe._clear_module(module)
        self.assertTrue(result["blocking"])
        self.assertEqual(result["issues"][0]["code"], "incompatible_abi")
        self.assertEqual(result["issues"][0]["file"], str(stale_file))

    def test_mixed_native_files_pass_only_when_module_imports(self):
        current = probe._expected_cpython_tag()
        stale = "311" if current != "311" else "314"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "fixture_mixed"
            package.mkdir()
            (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
            (package / f"_native.cpython-{stale}-darwin.so").touch()
            (package / f"_native.cpython-{current}-darwin.so").touch()
            passing = probe.run_probe(
                mode="preinstall",
                site_packages=root,
                modules=["fixture_mixed"],
            )
            (package / "__init__.py").write_text(
                "raise ImportError('fixture is broken')\n",
                encoding="utf-8",
            )
            failing = probe.run_probe(
                mode="preinstall",
                site_packages=root,
                modules=["fixture_mixed"],
            )
        self.assertFalse(passing["blocking"])
        self.assertTrue(failing["blocking"])
        self.assertEqual(failing["issues"][0]["code"], "import_failure")
        self.assertEqual(
            failing["issues"][0]["file"],
            str(package / f"_native.cpython-{current}-darwin.so"),
        )
        self.assertEqual(failing["issues"][0]["expected"], "successful import")
        self.assertIn("ImportError", failing["issues"][0]["detected"])

    def test_incompatible_abi_reports_exact_native_file(self):
        current = probe._expected_cpython_tag()
        stale = "311" if current != "311" else "314"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "fixture_abi"
            package.mkdir()
            native = package / f"_native.cpython-{stale}-darwin.so"
            native.touch()
            (package / "__init__.py").write_text(
                "from . import _native\n",
                encoding="utf-8",
            )
            result = probe.run_probe(
                mode="preinstall",
                site_packages=root,
                modules=["fixture_abi"],
            )
        issue = next(
            issue for issue in result["issues"] if issue["code"] == "incompatible_abi"
        )
        self.assertTrue(result["blocking"])
        self.assertEqual(issue["file"], str(native))
        self.assertIn(f"cpython-{stale}", issue["message"])

    def test_wrong_architecture_reports_deterministic_issue(self):
        current = probe._expected_cpython_tag()
        expected_arch = probe._runtime()["architecture"]
        wrong_arch = "x86_64" if expected_arch == "arm64" else "arm64"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "fixture_arch"
            package.mkdir()
            native = package / f"_native.cpython-{current}-darwin.so"
            native.touch()
            (package / "__init__.py").write_text(
                "from . import _native\n",
                encoding="utf-8",
            )
            with mock.patch.object(
                probe, "_macho_architectures", return_value=[wrong_arch]
            ):
                result = probe.run_probe(
                    mode="preinstall",
                    site_packages=root,
                    modules=["fixture_arch"],
                )
        issue = next(
            issue
            for issue in result["issues"]
            if issue["code"] == "incompatible_architecture"
        )
        self.assertTrue(result["blocking"])
        self.assertEqual(issue["file"], str(native))
        self.assertEqual(issue["detected"], wrong_arch)

    def test_partial_install_and_postinstall_missing_are_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "fixture_partial"
            package.mkdir()
            (package / "__init__.py").write_text(
                "from . import missing_native\n",
                encoding="utf-8",
            )
            preflight = probe.run_probe(
                mode="preinstall",
                site_packages=root,
                modules=["fixture_partial"],
            )
            postinstall = probe.run_probe(
                mode="postinstall",
                site_packages=root,
                allowed_origins=[root],
                modules=["fixture_missing_post"],
            )
        self.assertTrue(preflight["blocking"])
        self.assertEqual(preflight["issues"][0]["code"], "import_failure")
        self.assertEqual(preflight["issues"][0]["file"], str(package))
        self.assertTrue(postinstall["blocking"])
        self.assertEqual(postinstall["issues"][0]["code"], "missing_module")

    def test_postinstall_unexpected_origin_is_blocking(self):
        with tempfile.TemporaryDirectory() as module_directory, tempfile.TemporaryDirectory() as allowed_directory:
            module_root = Path(module_directory)
            (module_root / "fixture_origin.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
            )
            result = probe.run_probe(
                mode="postinstall",
                site_packages=module_root,
                allowed_origins=[Path(allowed_directory)],
                modules=["fixture_origin"],
            )
        self.assertTrue(result["blocking"])
        self.assertEqual(result["issues"][0]["code"], "unexpected_origin")


class PythonInstallerProbeProtocolTests(unittest.TestCase):
    def valid_payload(self, *, blocking=False, mode="preinstall"):
        return {
            "schemaVersion": 1,
            "mode": mode,
            "status": "incompatible" if blocking else "ok",
            "blocking": blocking,
            "runtime": {
                "executable": "/tmp/python",
                "version": "3.14.0",
                "implementation": "CPython",
                "soabi": "cpython-314-darwin",
                "extensionSuffix": ".cpython-314-darwin.so",
                "architecture": "arm64",
            },
            "sitePackages": "/tmp/site-packages",
            "checks": [],
            "issues": [],
        }

    def completed(self, stdout, *, stderr="", returncode=0):
        return subprocess.CompletedProcess([], returncode, stdout, stderr)

    def test_nonzero_exit_with_nonblocking_json_is_rejected(self):
        payload = json.dumps(self.valid_payload())
        with mock.patch.object(
            installer.subprocess,
            "run",
            return_value=self.completed(payload, returncode=7),
        ):
            with self.assertRaisesRegex(
                installer.RuntimeProbeError, "exited unexpectedly"
            ):
                installer.run_runtime_probe(
                    Path("/tmp/python"), Path("/tmp/site-packages"), "preinstall"
                )

    def test_malformed_json_is_rejected(self):
        with mock.patch.object(
            installer.subprocess,
            "run",
            return_value=self.completed("not-json"),
        ):
            with self.assertRaisesRegex(installer.RuntimeProbeError, "malformed JSON"):
                installer.run_runtime_probe(
                    Path("/tmp/python"), Path("/tmp/site-packages"), "preinstall"
                )

    def test_stderr_only_failure_is_rejected(self):
        payload = json.dumps(self.valid_payload())
        with mock.patch.object(
            installer.subprocess,
            "run",
            return_value=self.completed(payload, stderr="loader warning"),
        ):
            with self.assertRaisesRegex(
                installer.RuntimeProbeError, "unexpected error output"
            ):
                installer.run_runtime_probe(
                    Path("/tmp/python"), Path("/tmp/site-packages"), "preinstall"
                )

    def test_timeout_is_rejected(self):
        with mock.patch.object(
            installer.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["python"], 1),
        ):
            with self.assertRaisesRegex(installer.RuntimeProbeError, "timed out"):
                installer.run_runtime_probe(
                    Path("/tmp/python"),
                    Path("/tmp/site-packages"),
                    "preinstall",
                    timeout=1,
                )

    def test_custom_install_orders_preflight_before_pip_and_postinstall(self):
        events = []
        python = Path("/tmp/python3.14")
        requirements = REPO_ROOT / "requirements.txt"
        with mock.patch.object(
            installer,
            "check_runtime_preinstall",
            side_effect=lambda selected, target: events.append(
                ("preflight", selected, target)
            ),
        ), mock.patch.object(
            installer,
            "run",
            side_effect=lambda command, **kwargs: events.append(
                ("pip", command, kwargs)
            ),
        ), mock.patch.object(
            installer,
            "verify_runtime",
            side_effect=lambda selected, target, **kwargs: events.append(
                ("postinstall", selected, target, kwargs)
            )
            or True,
        ), mock.patch.object(
            installer,
            "python_version",
            return_value="3.14.2",
        ):
            installer.install_with_custom_python(
                python,
                requirements,
                glyphs_version="3",
            )

        self.assertEqual(
            [event[0] for event in events],
            ["preflight", "pip", "postinstall"],
        )
        expected_target = installer.glyphs_scripts_site_packages("3")
        self.assertEqual(events[0][1:], (python, expected_target))
        self.assertEqual(events[2][1:3], (python, expected_target))

    def test_blocking_preflight_prevents_pip(self):
        with mock.patch.object(
            installer,
            "check_runtime_preinstall",
            side_effect=SystemExit(2),
        ), mock.patch.object(installer, "run") as pip:
            with self.assertRaises(SystemExit) as raised:
                installer.install_with_custom_python(
                    Path("/tmp/python3.14"),
                    REPO_ROOT / "requirements.txt",
                )
        self.assertEqual(raised.exception.code, 2)
        pip.assert_not_called()

    def test_noninteractive_preflight_failure_prevents_plugin_install(self):
        options = installer.InstallerOptions(
            non_interactive=True,
            python_mode="custom",
            python_path=Path("/tmp/python3.14"),
            plugin_mode="link",
            install_skills=False,
            overwrite_plugin=True,
            show_client_guidance=False,
        )
        with mock.patch.object(
            installer,
            "python_version",
            return_value="3.14.2",
        ), mock.patch.object(
            installer,
            "install_with_custom_python",
            side_effect=SystemExit(2),
        ), mock.patch.object(installer, "install_plugin") as plugin_install:
            with self.assertRaises(SystemExit) as raised:
                installer.run_non_interactive(
                    options,
                    REPO_ROOT / "requirements.txt",
                )
        self.assertEqual(raised.exception.code, 2)
        plugin_install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
