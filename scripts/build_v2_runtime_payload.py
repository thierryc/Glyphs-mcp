#!/usr/bin/env python3
"""Assemble identical v2 Python payloads for both plug-in bundle layouts."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import plistlib
import shutil
from pathlib import Path
from typing import Dict


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACKAGE = REPO_ROOT / "src" / "glyphs-mcp-v2" / "glyphs_mcp_v2"
SOURCE_BUNDLE = REPO_ROOT / "src" / "glyphs-mcp" / "Glyphs MCP.glyphsPlugin"
PLUGIN_MANAGER_BUNDLE = REPO_ROOT / "plugin-manager" / "Glyphs MCP.glyphsPlugin"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "build" / "v2-runtime"
BUNDLE_NAME = "Glyphs MCP.glyphsPlugin"
PACKAGE_RELATIVE_TO_BUNDLE = Path("Contents/Resources/glyphs_mcp_v2")

V2_MCP_TOOLS = '''# encoding: utf-8

"""Glyphs MCP 2.0 development runtime bridge.

This generated bridge deliberately registers only the isolated v2 catalog.
"""

from glyphs_mcp_v2.runtime import create_glyphs_server


mcp = create_glyphs_server()

__all__ = ["mcp"]
'''

V2_CHANGES_PANEL = '''# encoding: utf-8

"""Generated v2 bridge to the apply-first Changes panel."""

from glyphs_mcp_v2.change_review_panel import DocumentChangesPanelController

__all__ = ["DocumentChangesPanelController"]
'''

LEGACY_IMPORT_BLOCK_START = "    # Import MCP tools (this registers all the tools)\n"
LEGACY_IMPORT_BLOCK_END = "    import kerning_resources  # noqa: F401\n"
V2_IMPORT_BLOCK = '''    # Load only the isolated v2 catalog. The generated mcp_tools bridge
    # constructs the Glyphs-backed v2 application and FastMCP server.
    from mcp_tools import mcp  # noqa: F401
'''


def _assert_output_is_contained(output_root: Path) -> Path:
    resolved = output_root.resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("v2 build output must remain inside the repository worktree") from exc
    if resolved == REPO_ROOT.resolve():
        raise ValueError("refusing to use the repository root as build output")
    return resolved


def _ignore_generated(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name == "__pycache__" or name.endswith((".pyc", ".pyo"))
    }


def _v2_version() -> str:
    versions_path = SOURCE_PACKAGE / "versions.py"
    tree = ast.parse(versions_path.read_text(encoding="utf-8"), filename=str(versions_path))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SERVER_VERSION":
                    value = ast.literal_eval(node.value)
                    if isinstance(value, str) and value:
                        return value
    raise RuntimeError("glyphs_mcp_v2.versions does not define a static SERVER_VERSION")


def _activate_v2_bundle(bundle: Path) -> Path:
    resources = bundle / "Contents" / "Resources"
    package_destination = bundle / PACKAGE_RELATIVE_TO_BUNDLE
    if package_destination.exists():
        shutil.rmtree(package_destination)
    shutil.copytree(SOURCE_PACKAGE, package_destination, ignore=_ignore_generated)

    (resources / "mcp_tools.py").write_text(V2_MCP_TOOLS, encoding="utf-8")
    (resources / "document_changes_panel.py").write_text(V2_CHANGES_PANEL, encoding="utf-8")

    plugin_path = resources / "plugin.py"
    plugin_text = plugin_path.read_text(encoding="utf-8")
    start = plugin_text.find(LEGACY_IMPORT_BLOCK_START)
    end = plugin_text.find(LEGACY_IMPORT_BLOCK_END, start)
    if start < 0 or end < 0:
        raise RuntimeError("could not locate the legacy registration block in plugin.py")
    end += len(LEGACY_IMPORT_BLOCK_END)
    plugin_text = plugin_text[:start] + V2_IMPORT_BLOCK + plugin_text[end:]
    plugin_text = plugin_text.replace(
        "from glyphs_candidate_reporter import GlyphsMCPCandidateReporter",
        "from glyphs_mcp_v2.change_review_reporter import GlyphsMCPChangeReviewReporter",
    )
    plugin_text = plugin_text.replace("GlyphsMCPCandidateReporter", "GlyphsMCPChangeReviewReporter")
    plugin_text = plugin_text.replace("Glyphs MCP Candidate (unavailable)", "Glyphs MCP Changes (unavailable)")
    plugin_path.write_text(plugin_text, encoding="utf-8")

    for legacy_name in (
        "glyphs_candidate_reporter.py",
        "outline_candidate_state.py",
        "mcp_tools_outline_candidates.py",
    ):
        legacy_path = resources / legacy_name
        if legacy_path.exists():
            legacy_path.unlink()

    plist_path = bundle / "Contents" / "Info.plist"
    with plist_path.open("rb") as plist_file:
        info = plistlib.load(plist_file)
    version = _v2_version()
    info["CFBundleShortVersionString"] = version
    info["CFBundleVersion"] = version
    principal_classes = [
        "GlyphsMCPChangeReviewReporter" if value == "GlyphsMCPCandidateReporter" else value
        for value in info.get("Principal Classes", [])
    ]
    info["Principal Classes"] = principal_classes
    with plist_path.open("wb") as plist_file:
        plistlib.dump(info, plist_file, sort_keys=True)
    return package_destination


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
    for bundle in (SOURCE_BUNDLE, PLUGIN_MANAGER_BUNDLE):
        if not bundle.is_dir():
            raise FileNotFoundError("base plug-in bundle is missing: {}".format(bundle))
    output = _assert_output_is_contained(output_root)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    sources = {
        "source": SOURCE_BUNDLE,
        "pluginManager": PLUGIN_MANAGER_BUNDLE,
    }
    destinations: Dict[str, Path] = {}
    bundle_paths: Dict[str, Path] = {}
    for name, source_bundle in sources.items():
        layout = "plugin-manager" if name == "pluginManager" else "source"
        destination_bundle = output / layout / BUNDLE_NAME
        destination_bundle.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_bundle, destination_bundle, ignore=_ignore_generated)
        bundle_paths[name] = destination_bundle
        destinations[name] = _activate_v2_bundle(destination_bundle)

    manifests = {name: _manifest(path) for name, path in destinations.items()}
    if manifests["source"] != manifests["pluginManager"]:
        raise RuntimeError("assembled v2 runtime payloads differ")

    result: Dict[str, object] = {
        "schemaVersion": 1,
        "sourcePackage": str(SOURCE_PACKAGE),
        "outputRoot": str(output),
        "version": _v2_version(),
        "installableBundle": str(bundle_paths["source"]),
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
