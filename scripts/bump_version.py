#!/usr/bin/env python3
"""
Bump the project version across native bundles, agent plugins, installer, and docs.

Usage:
  python3 scripts/bump_version.py [--dry-run] X.Y.Z
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
AGENT_PLUGIN_MANIFEST_PATHS = (
    Path("plugins/glyphs-mcp/.codex-plugin/plugin.json"),
    Path("plugins/glyphs-mcp/.claude-plugin/plugin.json"),
    Path("plugins/glyphs-mcp/.cursor-plugin/plugin.json"),
    Path("plugins/glyphs-mcp/.github/plugin/plugin.json"),
)
AGENT_PLUGIN_DOC_REPLACEMENTS = {
    Path("README.md"): (
        re.compile(r"(Glyphs MCP )\d+\.\d+\.\d+( provides one shared plugin package)"),
        re.compile(r"(All host manifests use version `)\d+\.\d+\.\d+(`)"),
    ),
    Path("plugins/glyphs-mcp/README.md"): (
        re.compile(r"(Version )\d+\.\d+\.\d+( bundles the same general Glyphs)"),
    ),
    Path("content/getting-started/use-agent-skills.mdx"): (
        re.compile(r"(All four manifests use version `)\d+\.\d+\.\d+(`)"),
        re.compile(r"(prepare version )\d+\.\d+\.\d+( and stop before external publication)"),
    ),
    Path("content/getting-started/installation.mdx"): (
        re.compile(r"(Agent plugins are a separate, optional setup\. Version )\d+\.\d+\.\d+( includes one shared)"),
    ),
    Path("content/contributor/release-qa-protocol.mdx"): (
        re.compile(r"(Each host resolves version `)\d+\.\d+\.\d+(`)"),
    ),
}


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


def update_json_version(path: Path, version: str) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: could not read JSON manifest {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        raise SystemExit(f"error: plugin manifest must contain a string name: {path}")
    data["version"] = version
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def update_agent_plugin_doc(
    path: Path,
    version: str,
    patterns: tuple[re.Pattern[str], ...],
) -> None:
    text = path.read_text(encoding="utf-8")
    original = text
    for pattern in patterns:
        text, count = pattern.subn(lambda match: f"{match.group(1)}{version}{match.group(2)}", text)
        if count != 1:
            raise SystemExit(
                f"error: expected exactly one agent-plugin version match in {path} "
                f"for {pattern.pattern!r}, found {count}"
            )
    if text != original:
        path.write_text(text, encoding="utf-8")


_README_COMMAND_SET_HEADER_RE = re.compile(r"^(##\s+Command Set\s+\(MCP server v)([^)]+)(\))[ \t]*$", re.M)
_FAST_MCP_VERSION_RE = re.compile(r"(FastMCP\s+`version=\")([^\"]+)(\"`)")
_README_SERVER_VERSION_RE = re.compile(r"(shipped in this repo \(version `)(\d+\.\d+\.\d+)(`\))")
_README_INSTALLER_URL_RE = re.compile(
    r"https://github\.com/thierryc/Glyphs-mcp/releases/(?:download/v\d+\.\d+\.\d+|latest/download)/GlyphsMCPInstaller(?:-\d+\.\d+\.\d+)?\.(dmg|zip)"
)
_RELEASE_TAG_URL_RE = re.compile(
    r"https://github\.com/thierryc/Glyphs-mcp/releases/tag/v\d+\.\d+\.\d+"
)
_VERSIONED_INSTALLER_URL_RE = re.compile(
    r"https://github\.com/thierryc/Glyphs-mcp/releases/download/v\d+\.\d+\.\d+/GlyphsMCPInstaller(?:-\d+\.\d+\.\d+)?\.(dmg|zip)"
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
    server_version_m = _README_SERVER_VERSION_RE.search(text)
    if not fastmcp_m and not server_version_m:
        raise SystemExit(
            f"error: could not find the server version mention in {readme_path} "
            "(expected the generic server version or FastMCP version wording)"
        )

    # 1) Command Set header: "## Command Set (MCP server vX.Y.Z)"
    text, n1 = _README_COMMAND_SET_HEADER_RE.subn(rf"\g<1>{version}\g<3>", text)
    if n1 != 1:
        raise SystemExit(f"error: expected to update 1 Command Set header in {readme_path}, updated {n1}")

    # 2) Server version mention. Keep compatibility with README revisions that
    # used either the older FastMCP-specific wording or the current generic one.
    text, fastmcp_count = _FAST_MCP_VERSION_RE.subn(rf"\g<1>{version}\g<3>", text)
    text, generic_count = _README_SERVER_VERSION_RE.subn(rf"\g<1>{version}\g<3>", text)
    if fastmcp_count + generic_count < 1:
        raise SystemExit(f"error: expected to update a server version mention in {readme_path}, found none")

    # 3) Installer download URLs:
    def _installer_url_repl(match: re.Match[str]) -> str:
        ext = match.group(1)
        return f"https://github.com/thierryc/Glyphs-mcp/releases/latest/download/GlyphsMCPInstaller.{ext}"

    text, n3 = _README_INSTALLER_URL_RE.subn(_installer_url_repl, text)
    if n3 < 1:
        raise SystemExit(
            f"error: could not find installer URL in {readme_path} (expected releases/latest/download/GlyphsMCPInstaller.(dmg|zip) or releases/download/vX.Y.Z/GlyphsMCPInstaller[-X.Y.Z].(dmg|zip))"
        )

    text, n4 = _RELEASE_TAG_URL_RE.subn(
        f"https://github.com/thierryc/Glyphs-mcp/releases/tag/v{version}",
        text,
    )
    if n4 < 1 and "https://github.com/thierryc/Glyphs-mcp/releases/latest" not in text:
        raise SystemExit(
            f"error: could not find release URL in {readme_path} (expected releases/tag/vX.Y.Z or releases/latest)"
        )

    if text != original:
        readme_path.write_text(text, encoding="utf-8")


def update_command_set_mdx(path: Path, version: str) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text

    if not _FAST_MCP_VERSION_RE.search(text):
        return False
    text, n = _FAST_MCP_VERSION_RE.subn(rf"\g<1>{version}\g<3>", text)
    if n < 1:
        raise SystemExit(f"error: expected to update FastMCP version mention in {path}, found none")

    if text != original:
        path.write_text(text, encoding="utf-8")
    return True


def update_installation_doc(path: Path, version: str) -> None:
    text = path.read_text(encoding="utf-8")
    original = text

    text, n1 = _RELEASE_TAG_URL_RE.subn(
        f"https://github.com/thierryc/Glyphs-mcp/releases/tag/v{version}",
        text,
    )
    if n1 < 1 and "https://github.com/thierryc/Glyphs-mcp/releases/latest" not in text:
        raise SystemExit(
            f"error: could not find release URL in {path} (expected releases/tag/vX.Y.Z or releases/latest)"
        )

    def _installer_url_repl(match: re.Match[str]) -> str:
        ext = match.group(1)
        return f"https://github.com/thierryc/Glyphs-mcp/releases/download/v{version}/GlyphsMCPInstaller.{ext}"

    text, n2 = _VERSIONED_INSTALLER_URL_RE.subn(_installer_url_repl, text)
    if n2 < 1 and "https://github.com/thierryc/Glyphs-mcp/releases/latest/download/GlyphsMCPInstaller." not in text:
        raise SystemExit(
            f"error: could not find installer URL in {path} (expected releases/download/vX.Y.Z/GlyphsMCPInstaller.(dmg|zip) or releases/latest/download/GlyphsMCPInstaller.(dmg|zip))"
        )

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
    args = argv[1:]
    dry_run = False
    if args[:1] == ["--dry-run"]:
        dry_run = True
        args = args[1:]
    if len(args) != 1:
        print(__doc__.strip())
        return 2

    version = args[0].strip()
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
    installation_doc_path = repo_root / "content" / "getting-started" / "installation.mdx"
    pbxproj_path = (
        repo_root
        / "macos-installer"
        / "GlyphsMCPInstaller"
        / "GlyphsMCPInstaller.xcodeproj"
        / "project.pbxproj"
    )
    agent_plugin_manifest_paths = tuple(repo_root / path for path in AGENT_PLUGIN_MANIFEST_PATHS)
    agent_plugin_doc_replacements = {
        repo_root / path: patterns for path, patterns in AGENT_PLUGIN_DOC_REPLACEMENTS.items()
    }

    required_paths = (
        src_plist_path,
        readme_path,
        command_set_path,
        installation_doc_path,
        pbxproj_path,
        *agent_plugin_manifest_paths,
        *agent_plugin_doc_replacements,
    )
    missing_paths = [path for path in required_paths if not path.exists()]
    if missing_paths:
        for path in missing_paths:
            print(f"error: required release surface not found at: {path}", file=sys.stderr)
        return 1

    temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    if dry_run:
        temporary_directory = tempfile.TemporaryDirectory(prefix="glyphs-mcp-version-dry-run.")
        temporary_root = Path(temporary_directory.name)
        working_paths: dict[Path, Path] = {}

        def working_path(path: Path) -> Path:
            if path in working_paths:
                return working_paths[path]
            destination = temporary_root / path.relative_to(repo_root)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            working_paths[path] = destination
            return destination

    else:

        def working_path(path: Path) -> Path:
            return path

    try:
        set_plist_key(working_path(src_plist_path), "CFBundleShortVersionString", version)
        set_plist_key(working_path(src_plist_path), "CFBundleVersion", version)
        if plugin_manager_plist_path.exists():
            set_plist_key(working_path(plugin_manager_plist_path), "CFBundleShortVersionString", version)
            set_plist_key(working_path(plugin_manager_plist_path), "CFBundleVersion", version)
        update_readme(working_path(readme_path), version)
        updated_command_set = update_command_set_mdx(working_path(command_set_path), version)
        update_installation_doc(working_path(installation_doc_path), version)
        update_marketing_version(working_path(pbxproj_path), version)
        for manifest_path in agent_plugin_manifest_paths:
            update_json_version(working_path(manifest_path), version)
        for doc_path, patterns in agent_plugin_doc_replacements.items():
            update_agent_plugin_doc(working_path(doc_path), version, patterns)
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()

    print("Would update:" if dry_run else "Updated:")
    print(f"  - {src_plist_path} (CFBundleShortVersionString, CFBundleVersion) -> {version}")
    if plugin_manager_plist_path.exists():
        print(f"  - {plugin_manager_plist_path} (CFBundleShortVersionString, CFBundleVersion) -> {version}")
    print(f"  - {readme_path} (installer URLs + Command Set + FastMCP version mention) -> {version}")
    if updated_command_set:
        print(f"  - {command_set_path} (FastMCP version mention) -> {version}")
    else:
        print(f"  - {command_set_path} (no FastMCP version mention; skipped)")
    print(f"  - {installation_doc_path} (release links) -> {version}")
    print(f"  - {pbxproj_path} (MARKETING_VERSION) -> {version}")
    for manifest_path in agent_plugin_manifest_paths:
        print(f"  - {manifest_path} (agent plugin version) -> {version}")
    for doc_path in agent_plugin_doc_replacements:
        print(f"  - {doc_path} (agent plugin documentation version) -> {version}")
    if dry_run:
        print("Dry run complete; repository files were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
