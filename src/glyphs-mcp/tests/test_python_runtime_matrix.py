"""Opt-in dependency verification across supported local Python runtimes.

Set GLYPHS_MCP_FULL_PYTHON_MATRIX=1 to create temporary virtual environments
and verify pinned requirements install and import under Python 3.12 and 3.14.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


FULL_MATRIX_ENV = "GLYPHS_MCP_FULL_PYTHON_MATRIX"
PYTHON_BINARIES = ("python3.12", "python3.14")
IMPORT_MODULES = (
    "mcp",
    "fastmcp",
    "pydantic_core",
    "starlette",
    "uvicorn",
    "httpx",
    "sse_starlette",
    "fontParts",
    "fontTools",
    "objc",
    "Foundation",
    "AppKit",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class PythonRequirementsTests(unittest.TestCase):
    def test_uses_only_required_pyobjc_components(self) -> None:
        lines = {
            line.strip()
            for line in (_repo_root() / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

        self.assertIn("pyobjc-core==11.1", lines)
        self.assertIn("pyobjc-framework-Cocoa==11.1", lines)
        self.assertNotIn("pyobjc==11.1", lines)

    def test_development_requirements_extend_runtime_without_shipping_test_tools(self) -> None:
        root = _repo_root()
        development = {
            line.strip()
            for line in (root / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        runtime = (root / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("-r requirements.txt", development)
        self.assertIn("glyphsLib==6.10.1", development)
        self.assertIn("pytest==8.4.2", development)
        self.assertNotIn("glyphsLib", runtime)
        self.assertNotIn("pytest", runtime)

    def test_python_test_runner_preflights_and_isolates_optional_pytest(self) -> None:
        runner = (_repo_root() / "scripts" / "run_python_tests.sh").read_text(encoding="utf-8")

        self.assertIn("requirements-dev.txt", runner)
        self.assertIn("Python 3.11-3.14", runner)
        self.assertIn("PYTEST_DISABLE_PLUGIN_AUTOLOAD=1", runner)
        self.assertIn("-m unittest discover", runner)


@unittest.skipUnless(
    os.environ.get(FULL_MATRIX_ENV) == "1",
    f"set {FULL_MATRIX_ENV}=1 to run full Python dependency verification",
)
class PythonRuntimeMatrixTests(unittest.TestCase):
    maxDiff = None

    def run_checked(self, cmd: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            cmd,
            cwd=_repo_root(),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=900,
        )
        if result.returncode != 0:
            self.fail(
                "Command failed:\n"
                f"{' '.join(cmd)}\n\n"
                f"stdout:\n{result.stdout}\n\n"
                f"stderr:\n{result.stderr}"
            )
        return result

    def test_requirements_install_and_import_under_python_312_and_314(self) -> None:
        missing = [name for name in PYTHON_BINARIES if shutil.which(name) is None]
        if missing:
            self.fail(f"Missing required Python runtimes on PATH: {', '.join(missing)}")

        requirements = _repo_root() / "requirements.txt"
        import_script = "\n".join(
            [
                "import importlib",
                f"modules = {list(IMPORT_MODULES)!r}",
                "for module in modules:",
                "    importlib.import_module(module)",
                "print('imports ok')",
            ]
        )

        for binary in PYTHON_BINARIES:
            with self.subTest(binary=binary):
                interpreter = shutil.which(binary)
                self.assertIsNotNone(interpreter)

                with tempfile.TemporaryDirectory(prefix=f"glyphs-mcp-{binary}-") as tmp:
                    venv_dir = Path(tmp) / "venv"
                    self.run_checked([interpreter, "-m", "venv", str(venv_dir)])

                    venv_python = venv_dir / "bin" / "python"
                    env = os.environ.copy()
                    env["PYTHONNOUSERSITE"] = "1"
                    env.pop("PYTHONPATH", None)

                    self.run_checked([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], env=env)
                    self.run_checked(
                        [
                            str(venv_python),
                            "-m",
                            "pip",
                            "install",
                            "--only-binary=:all:",
                            "--no-compile",
                            "-r",
                            str(requirements),
                        ],
                        env=env,
                    )
                    self.run_checked([str(venv_python), "-c", import_script], env=env)


if __name__ == "__main__":
    unittest.main()
