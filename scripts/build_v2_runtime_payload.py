#!/usr/bin/env python3
"""Assemble identical v2 Python payloads for both plug-in bundle layouts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Dict


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACKAGE = REPO_ROOT / "src" / "glyphs-mcp-v2" / "glyphs_mcp_v2"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "build" / "v2-runtime"
BUNDLE_RELATIVE_PACKAGE = Path("Glyphs MCP.glyphsPlugin/Contents/Resources/glyphs_mcp_v2")


def _assert_output_is_contained(output_root: Path) -> Path:
    resolved = output_root.resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("v2 build output must remain inside the repository worktree") from exc
    if resolved == REPO_ROOT.resolve():
        raise ValueError("refusing to use the repository root as build output")
    return resolved


def _copy_package(destination: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {
            name
            for name in names
            if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
        }

    shutil.copytree(SOURCE_PACKAGE, destination, ignore=ignore)


def _manifest(package_root: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for path in sorted(package_root.rglob("*")):
        if path.is_file():
            values[path.relative_to(package_root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return values


def build(output_root: Path) -> Dict[str, object]:
    if not SOURCE_PACKAGE.is_dir():
        raise FileNotFoundError("canonical v2 package is missing: {}".format(SOURCE_PACKAGE))
    output = _assert_output_is_contained(output_root)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    destinations = {
        "source": output / "source" / BUNDLE_RELATIVE_PACKAGE,
        "pluginManager": output / "plugin-manager" / BUNDLE_RELATIVE_PACKAGE,
    }
    for destination in destinations.values():
        destination.parent.mkdir(parents=True, exist_ok=True)
        _copy_package(destination)

    manifests = {name: _manifest(path) for name, path in destinations.items()}
    if manifests["source"] != manifests["pluginManager"]:
        raise RuntimeError("assembled v2 runtime payloads differ")

    result: Dict[str, object] = {
        "schemaVersion": 1,
        "sourcePackage": str(SOURCE_PACKAGE),
        "outputRoot": str(output),
        "fileCount": len(manifests["source"]),
        "files": manifests["source"],
    }
    (output / "manifest.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="worktree-contained output directory (default: build/v2-runtime)",
    )
    args = parser.parse_args()
    result = build(args.output_root)
    print(
        "Assembled {fileCount} v2 runtime files in {outputRoot}".format(**result)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
