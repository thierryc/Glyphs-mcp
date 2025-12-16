#!/usr/bin/env python3
"""Download and extract wheels for bundling into the plugin.

This script downloads pre-built wheels for the current Python version and platform,
then extracts them into the plugin's vendor/ directory for zero-config installation.

Usage:
    python3.11 scripts/vendor_deps.py   # bundles for Python 3.11
    python3.14 scripts/vendor_deps.py   # bundles for Python 3.14
"""

import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent.parent  # src/glyphs-mcp/scripts -> repo root
REQUIREMENTS = REPO_ROOT / "requirements.txt"
VENDOR_DIR = (
    REPO_ROOT
    / "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Resources/vendor"
)


def get_python_version() -> str:
    """Return the major.minor Python version string."""
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def main() -> int:
    py_version = get_python_version()
    py_platform = platform.platform()

    if not REQUIREMENTS.exists():
        print(
            f"Error: {REQUIREMENTS} not found.\n"
            "Run 'uv pip compile pyproject.toml --upgrade -o requirements.txt' first.",
            file=sys.stderr,
        )
        return 1

    print(f"Python: {py_version} ({sys.executable})")
    print(f"Platform: {py_platform}")
    print(f"Requirements: {REQUIREMENTS}")
    print(f"Vendor dir: {VENDOR_DIR}")
    print()

    # Clean vendor directory
    if VENDOR_DIR.exists():
        print(f"Cleaning existing vendor directory...")
        shutil.rmtree(VENDOR_DIR)
    VENDOR_DIR.mkdir(parents=True)

    # Download wheels to temp dir
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        print("Downloading wheels...")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "-r",
                str(REQUIREMENTS),
                "-d",
                str(tmp_path),
            ],
            check=False,
        )
        if result.returncode != 0:
            print("Error: pip download failed", file=sys.stderr)
            return 1

        # Extract all wheels
        wheels = sorted(tmp_path.glob("*.whl"))
        print(f"\nExtracting {len(wheels)} wheels...")
        for whl in wheels:
            print(f"  {whl.name}")
            with zipfile.ZipFile(whl) as zf:
                zf.extractall(VENDOR_DIR)

        # Calculate total size
        total_size = sum(
            f.stat().st_size for f in VENDOR_DIR.rglob("*") if f.is_file()
        )
        print(f"\nVendored {len(wheels)} packages to {VENDOR_DIR}")
        print(f"Total size: {total_size / 1024 / 1024:.1f} MB")

    return 0


if __name__ == "__main__":
    sys.exit(main())
