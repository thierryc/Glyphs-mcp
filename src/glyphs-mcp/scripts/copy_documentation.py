#!/usr/bin/env python3
"""Synchronise the bundled MCP documentation into the plug-in resources.

This helper copies the Sphinx-generated documentation that ships with the
Glyphs SDK ObjectWrapper into the plug-in bundle so the MCP server can serve it
without depending on the SDK folder at runtime.

By default the script expects the generated docs to live at
``GlyphsSDK/ObjectWrapper/MCP Documentation`` relative to the repository root
and copies the contents into
``src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Resources/MCP Documentation``.

Run ``python src/glyphs-mcp/scripts/copy_documentation.py`` from the repository root after
regenerating the docs to refresh the bundled resources. Use ``--source`` and
``--destination`` to override the default locations if needed.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = REPO_ROOT / "GlyphsSDK" / "ObjectWrapper" / "MCP Documentation"
DEFAULT_DESTINATION = (
    REPO_ROOT
    / "src"
    / "glyphs-mcp"
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
    / "MCP Documentation"
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="Path to the generated MCP documentation (defaults to the SDK output).",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=DEFAULT_DESTINATION,
        help="Destination folder inside the plug-in bundle.",
    )
    return parser.parse_args(argv)


def _validate_source(source: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Documentation source directory not found: {source}")
    if not source.is_dir():
        raise NotADirectoryError(f"Documentation source must be a directory: {source}")


def _clean_destination(destination: Path) -> None:
    if not destination.exists():
        destination.mkdir(parents=True, exist_ok=True)
        return

    for entry in destination.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def _copy_item(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def copy_documentation(source: Path, destination: Path) -> None:
    """Copy documentation files from ``source`` into ``destination``."""

    _validate_source(source)
    if source.resolve() == destination.resolve():
        raise ValueError("Source and destination must be different paths")
    _clean_destination(destination)

    for entry in source.iterdir():
        target = destination / entry.name
        _copy_item(entry, target)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        copy_documentation(args.source, args.destination)
    except Exception as exc:  # pragma: no cover - CLI helper
        print(f"Error copying documentation: {exc}", file=sys.stderr)
        return 1

    print(f"Copied documentation from {args.source} to {args.destination}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
