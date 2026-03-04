#!/usr/bin/env python3
"""
Bump the project version across the plug-in bundle, installer, and docs.

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


_README_COMMAND_SET_HEADER_RE = re.compile(r"^(##\s+Command Set\s+\(MCP server v)([^)]+)(\))\s*$", re.M)
_FAST_MCP_VERSION_RE = re.compile(r"(FastMCP\s+`version=\")([^\"]+)(\"`)")
_README_INSTALLER_URL_RE = re.compile(
    r"(https://github\.com/thierryc/Glyphs-mcp/releases/download/v)(\d+\.\d+\.\d+)(/GlyphsMCPInstaller-)(\d+\.\d+\.\d+)(\.dmg)"
)
_PBXPROJ_MARKETING_VERSION_RE = re.compile(r"(\bMARKETING_VERSION\s*=\s*)(\d+\.\d+\.\d+)(\s*;)")


def update_readme(readme_path: Path, version: str) -> None:
    text = readme_path.read_text(encoding="utf-8")
    original = text

    header_m = _README_COMMAND_SET_HEADER_RE.search(text)
    if not header_m:
        raise SystemExit(
            f"error: could not find Command Set header in {readme_path} (expected: '## Command Set (MCP server vX.Y.Z)')"
        )

    fastmcp_m = _FAST_MCP_VERSION_RE.search(text)
    if not fastmcp_m:
        raise SystemExit(
            f"error: could not find FastMCP version mention in {readme_path} (expected: FastMCP `version=\"X.Y.Z\"`)"
        )

    # 1) Command Set header: "## Command Set (MCP server vX.Y.Z)"
    text, n1 = _README_COMMAND_SET_HEADER_RE.subn(rf"\g<1>{version}\g<3>", text)
    if n1 != 1:
        raise SystemExit(f"error: expected to update 1 Command Set header in {readme_path}, updated {n1}")

    # 2) FastMCP version mention:
    text, n2 = _FAST_MCP_VERSION_RE.subn(rf"\g<1>{version}\g<3>", text)
    if n2 < 1:
        raise SystemExit(f"error: expected to update FastMCP version mention in {readme_path}, found none")

    # 3) Installer download URL (versioned):
    text, n3 = _README_INSTALLER_URL_RE.subn(rf"\g<1>{version}\g<3>{version}\g<5>", text)
    if n3 < 1:
        raise SystemExit(
            f"error: could not find versioned installer DMG URL in {readme_path} (expected releases/download/vX.Y.Z/GlyphsMCPInstaller-X.Y.Z.dmg)"
        )

    if text != original:
        readme_path.write_text(text, encoding="utf-8")


def update_command_set_mdx(path: Path, version: str) -> None:
    text = path.read_text(encoding="utf-8")
    original = text

    if not _FAST_MCP_VERSION_RE.search(text):
        raise SystemExit(
            f"error: could not find FastMCP version mention in {path} (expected: FastMCP `version=\"X.Y.Z\"`)"
        )
    text, n = _FAST_MCP_VERSION_RE.subn(rf"\g<1>{version}\g<3>", text)
    if n < 1:
        raise SystemExit(f"error: expected to update FastMCP version mention in {path}, found none")

    if text != original:
        path.write_text(text, encoding="utf-8")


def update_marketing_version(pbxproj_path: Path, version: str) -> None:
    text = pbxproj_path.read_text(encoding="utf-8")
    original = text

    text, n = _PBXPROJ_MARKETING_VERSION_RE.subn(rf"\g<1>{version}\g<3>", text)
    if n < 1:
        raise SystemExit(f"error: could not find MARKETING_VERSION assignments in {pbxproj_path}")

    if text != original:
        pbxproj_path.write_text(text, encoding="utf-8")


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
    src_plist_path = (
        repo_root
        / "src"
        / "glyphs-mcp"
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Info.plist"
    )
    plugin_manager_plist_path = (
        repo_root
        / "plugin-manager"
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Info.plist"
    )
    readme_path = repo_root / "README.md"
    command_set_path = repo_root / "content" / "reference" / "command-set.mdx"
    pbxproj_path = (
        repo_root
        / "macos-installer"
        / "GlyphsMCPInstaller"
        / "GlyphsMCPInstaller.xcodeproj"
        / "project.pbxproj"
    )

    if not src_plist_path.exists():
        print(f"error: Info.plist not found at: {src_plist_path}", file=sys.stderr)
        return 1
    if not readme_path.exists():
        print(f"error: README not found at: {readme_path}", file=sys.stderr)
        return 1
    if not command_set_path.exists():
        print(f"error: command set doc not found at: {command_set_path}", file=sys.stderr)
        return 1
    if not pbxproj_path.exists():
        print(f"error: installer pbxproj not found at: {pbxproj_path}", file=sys.stderr)
        return 1

    set_plist_key(src_plist_path, "CFBundleShortVersionString", version)
    set_plist_key(src_plist_path, "CFBundleVersion", version)
    if plugin_manager_plist_path.exists():
        set_plist_key(plugin_manager_plist_path, "CFBundleShortVersionString", version)
        set_plist_key(plugin_manager_plist_path, "CFBundleVersion", version)
    update_readme(readme_path, version)
    update_command_set_mdx(command_set_path, version)
    update_marketing_version(pbxproj_path, version)

    print("Updated:")
    print(f"  - {src_plist_path} (CFBundleShortVersionString, CFBundleVersion) -> {version}")
    if plugin_manager_plist_path.exists():
        print(f"  - {plugin_manager_plist_path} (CFBundleShortVersionString, CFBundleVersion) -> {version}")
    print(f"  - {readme_path} (download URL + Command Set + FastMCP version mention) -> {version}")
    print(f"  - {command_set_path} (FastMCP version mention) -> {version}")
    print(f"  - {pbxproj_path} (MARKETING_VERSION) -> {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
