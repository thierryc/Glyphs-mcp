"""Tests for the fail-closed release dependency preflight."""

from __future__ import annotations

from importlib import metadata
import importlib.util
from pathlib import Path
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/check_release_dependencies.py"
SPEC = importlib.util.spec_from_file_location("check_release_dependencies", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
dependency_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dependency_check)


class ReleaseDependencyPreflightTests(unittest.TestCase):
    def _requirements(self, contents: str, root: str) -> Path:
        path = Path(root) / "requirements-dev.txt"
        path.write_text(contents, encoding="utf-8")
        return path

    def test_accepts_the_one_exact_installed_pin(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            requirements = self._requirements(
                "# build tools\nfontmake==3.10.1\npytest==8.4.2\n",
                root,
            )

            expected, observed = dependency_check.verify_exact_dependency(
                requirements,
                "fontmake",
                version_reader=lambda _package: "3.10.1",
            )

        self.assertEqual((expected, observed), ("3.10.1", "3.10.1"))

    def test_rejects_missing_unpinned_and_duplicate_requirements(self) -> None:
        cases = (
            ("pytest==8.4.2\n", "exactly one"),
            ("fontmake>=3.10.1\n", "unconditional exact pin"),
            ("fontmake==3.10.1\nfontmake==3.10.1\n", "exactly one"),
            ("fontmake==3.10.1; python_version > '3.11'\n", "unconditional exact pin"),
        )
        for contents, message in cases:
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as root:
                requirements = self._requirements(contents, root)
                with self.assertRaisesRegex(RuntimeError, message):
                    dependency_check.read_exact_pin(requirements, "fontmake")

    def test_rejects_missing_or_mismatched_installed_distribution(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            requirements = self._requirements("fontmake==3.10.1\n", root)

            with self.assertRaisesRegex(RuntimeError, "is not installed"):
                dependency_check.verify_exact_dependency(
                    requirements,
                    "fontmake",
                    version_reader=lambda package: (_ for _ in ()).throw(
                        metadata.PackageNotFoundError(package)
                    ),
                )
            with self.assertRaisesRegex(RuntimeError, "but .* pins 3.10.1"):
                dependency_check.verify_exact_dependency(
                    requirements,
                    "fontmake",
                    version_reader=lambda _package: "3.9.0",
                )


if __name__ == "__main__":
    unittest.main()
