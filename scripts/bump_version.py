#!/usr/bin/env python3
"""
Bump the plugin version in Info.plist and README.

Usage:
  python3 scripts/bump_version.py X.Y.Z
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def set_plist_key(plist_path: Path, key: str, value: str) -> None:
    plistbuddy = Path("/usr/libexec/PlistBuddy")
    if plistbuddy.exists() and plistbuddy.is_file():
        try:
            run([str(plistbuddy), "-c", f"Set :{key} {value}", str(plist_path)])
            return
        except subprocess.CalledProcessError:
            # Key might not exist in some forks; fall back to Add.
            run([str(plistbuddy), "-c", f"Add :{key} string {value}", str(plist_path)])
            return

    # Fallback (non-macOS): use plistlib, re-writing as XML.
    import plistlib

    with plist_path.open("rb") as f:
        data = plistlib.load(f)
    data[key] = value
    with plist_path.open("wb") as f:
        plistlib.dump(data, f, fmt=plistlib.FMT_XML, sort_keys=False)


def update_readme(readme_path: Path, version: str) -> None:
    text = readme_path.read_text(encoding="utf-8")
    original = text

    header_re = re.compile(r"^(##\s+Command Set\s+\(MCP server v)([^)]+)(\))\s*$", re.M)
    fastmcp_re = re.compile(r"(FastMCP\s+`version=\")([^\"]+)(\"`)")

    header_m = header_re.search(text)
    if not header_m:
        raise SystemExit(
            f"error: could not find Command Set header in {readme_path} (expected: '## Command Set (MCP server vX.Y.Z)')"
        )
    current_header_version = header_m.group(2)

    fastmcp_m = fastmcp_re.search(text)
    if not fastmcp_m:
        raise SystemExit(
            f"error: could not find FastMCP version mention in {readme_path} (expected: FastMCP `version=\"X.Y.Z\"`)"
        )
    current_fastmcp_version = fastmcp_m.group(2)

    if current_header_version == version and current_fastmcp_version == version:
        return

    # 1) Command Set header: "## Command Set (MCP server vX.Y.Z)"
    text, n1 = header_re.subn(rf"\g<1>{version}\g<3>", text)
    if n1 != 1:
        raise SystemExit(
            f"error: expected to update 1 Command Set header in {readme_path}, updated {n1}"
        )

    # 2) FastMCP version mention in that section:
    #    ... (FastMCP `version="X.Y.Z"`).
    text, n2 = fastmcp_re.subn(rf"\g<1>{version}\g<3>", text)
    if n2 < 1:
        raise SystemExit(
            f"error: expected to update FastMCP version mention in {readme_path}, found none"
        )

    if text != original:
        readme_path.write_text(text, encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] in {"-h", "--help"}:
        print(__doc__.strip())
        return 0
    if len(argv) != 2:
        print(__doc__.strip())
        return 2

    version = argv[1].strip()
    if not VERSION_RE.match(version):
        print(f"error: invalid version: {version!r} (expected X.Y.Z)", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parent.parent
    plist_path = (
        repo_root
        / "src"
        / "glyphs-mcp"
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Info.plist"
    )
    readme_path = repo_root / "README.md"

    if not plist_path.exists():
        print(f"error: Info.plist not found at: {plist_path}", file=sys.stderr)
        return 1
    if not readme_path.exists():
        print(f"error: README not found at: {readme_path}", file=sys.stderr)
        return 1

    set_plist_key(plist_path, "CFBundleShortVersionString", version)
    set_plist_key(plist_path, "CFBundleVersion", version)
    update_readme(readme_path, version)

    print("Updated:")
    print(f"  - {plist_path} (CFBundleShortVersionString, CFBundleVersion) -> {version}")
    print(f"  - {readme_path} (Command Set + FastMCP version mention) -> {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
