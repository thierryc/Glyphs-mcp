"""Lean build and size-budget contracts."""

from __future__ import annotations

import ast
import importlib.util
import sys
import json
import plistlib
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
BUILDER_PATH = REPO / "scripts" / "build_simple_v2.py"
SPEC = importlib.util.spec_from_file_location("build_simple_v2", BUILDER_PATH)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def _python_lines(root: Path) -> int:
    return sum(len(path.read_text(encoding="utf-8").splitlines()) for path in root.rglob("*.py"))


def test_build_is_deterministic_and_excludes_the_old_runtime(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    manifest_a = BUILDER.build(first)
    manifest_b = BUILDER.build(second)
    assert manifest_a == manifest_b
    assert json.loads((first / "manifest.json").read_text()) == manifest_a
    assert manifest_a["tools"] == [
        "get_status",
        "list_documents",
        "read_entities",
        "start_job",
        "get_job",
        "apply_job",
        "discard_job",
    ]
    names = {path.name for path in first.rglob("*.py")}
    assert "canonical_tree.py" not in names
    assert "transactions.py" not in names
    assert "headless_preview.py" not in names
    assert (first / "Glyphs MCP Bridge.glyphsPlugin" / "Contents" / "MacOS" / "plugin").is_file()
    info = plistlib.loads((first / "Glyphs MCP Bridge.glyphsPlugin/Contents/Info.plist").read_bytes())
    assert info["Principal Classes"] == ["GlyphsMCPServerPlugin", "GlyphsMCPBridgePlugin"]
    layout = json.loads((first / "Glyphs MCP Bridge.glyphsPlugin/Contents/Resources/glyphs_mcp_bridge/server_panel.json").read_text())
    assert layout["projectVersion"] == json.loads((REPO / "plugins/glyphs-mcp/.claude-plugin/plugin.json").read_text())["version"]
    assert (first / "Glyphs Curve Inspector.glyphsReporter").is_dir()
    assert (first / "Glyphs Reference Inspector.glyphsReporter").is_dir()
    assert [item["id"] for item in manifest_a["companions"]] == ["curve-inspector", "reference-inspector"]
    assert not any("Metadata Inspector" in path.name for path in first.rglob("*"))
    assert (first / "sidecar" / "curve_core" / "geometry.py").is_file()
    # Python imports this shared module from whichever bundle loads first.
    # Installing stale bridge helpers must not silently break both Reporters.
    sdk = (REPO / "src/companions/sdk/glyphs_mcp_companions.py").read_bytes()
    for bundle in (manifest_a["bridge"], *manifest_a["companions"]):
        resources = first / bundle["bundle"] / "Contents/Resources"
        assert (resources / "glyphs_mcp_companions.py").read_bytes() == sdk
    for identifier, package in (("curve-inspector", "glyphs_curve_inspector"),
                                ("reference-inspector", "glyphs_reference_inspector")):
        bundle = next(item for item in manifest_a["companions"] if item["id"] == identifier)
        resources = first / bundle["bundle"] / "Contents/Resources"
        source = (REPO / "src/companions" / identifier / package / "plugin.py").read_bytes()
        assert (resources / "plugin.py").read_bytes() == source
        assert (resources / package / "plugin.py").read_bytes() == source


def test_initial_core_is_below_reset_line_budgets() -> None:
    protocol = _python_lines(REPO / "src" / "protocol" / "glyphs_mcp_protocol")
    bridge = _python_lines(REPO / "src" / "bridge" / "glyphs_mcp_bridge")
    sidecar = _python_lines(REPO / "src" / "sidecar" / "glyphs_mcp_sidecar")
    # Explicit, bounded coordinate vectors and topology guards (benefit item 4).
    # Shared initialization-time fingerprint helper; editing contracts unchanged.
    assert protocol <= 425
    # Native setters for nodes, anchors and component matrices (benefit item 4).
    # Bounded native master pages and strict IDs add 53 lines; no new tool/history.
    # Compact selection context uses a small stateless read module; no new tool, job or history hooks.
    # Lazy native groups and restoration of their original automatic-grouping setting.
    # Existing inverse callbacks/history only; no additional recovery system.
    # H3 adds one stateless bounded context projection, preserving all editing hooks.
    # H4 adds bounded glyph pages with constant-size guards and no inventory cache.
    # H5 adds one stateless native layer inventory; editing/lifecycle hooks unchanged.
    # H6 adds stateless indexed kerning pages with a bounded work budget.
    assert bridge <= 2300
    assert sidecar <= 3500
    assert protocol + bridge + sidecar <= 6000
    assert all(
        len(path.read_text(encoding="utf-8").splitlines()) <= 500
        for root in (
            REPO / "src" / "protocol" / "glyphs_mcp_protocol",
            REPO / "src" / "bridge" / "glyphs_mcp_bridge",
            REPO / "src" / "sidecar" / "glyphs_mcp_sidecar",
        )
        for path in root.rglob("*.py")
    )


def test_bridge_has_no_mcp_or_experimental_runtime_dependency() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPO / "src" / "bridge" / "glyphs_mcp_bridge").rglob("*.py")
    )
    assert "import fastmcp" not in source
    assert "from fastmcp" not in source
    assert "glyphs_mcp_v2" not in source
    assert "canonical_tree" not in source
    assert "headless_preview" not in source


def test_bridge_is_a_fixed_minimal_palette_without_activity_ui() -> None:
    plugin = REPO / "src" / "bridge" / "glyphs_mcp_bridge" / "plugin.py"
    source = plugin.read_text(encoding="utf-8")
    tree = ast.parse(source)
    bridge_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GlyphsMCPBridgePlugin"
    )
    assert [ast.unparse(base) for base in bridge_class.bases] == ["PalettePlugin"]
    assert "GeneralPlugin" not in source
    assert "NSPanel" not in source
    assert "Last request" not in source
    assert "_record_activity" not in source
    assert "self.min = PALETTE_HEIGHT" in source
    assert "self.max = PALETTE_HEIGHT" in source
    assert '"Stopped" if bridge_lifecycle.stopped' in source
    assert '"Ready" if ready' in source
    assert '"Glyphs MCP Bridge {} ({})".format(PROJECT_VERSION, BRIDGE_VERSION)' in source
    assert "_details" not in source
    assert "PALETTE_HEIGHT = 30" in source


def test_source_wrappers_are_thin_and_built_entry_points_declare_one_principal() -> None:
    wrappers = (
        REPO
        / "src"
        / "bridge"
        / "bundle"
        / "Glyphs MCP Bridge.glyphsPlugin"
        / "Contents"
        / "Resources"
        / "plugin.py",
        REPO
        / "src"
        / "companions"
        / "curve-inspector"
        / "bundle"
        / "Glyphs Curve Inspector.glyphsReporter"
        / "Contents"
        / "Resources"
        / "plugin.py",
    )
    wrappers += (REPO / "src/companions/reference-inspector/bundle/Glyphs Reference Inspector.glyphsReporter/Contents/Resources/plugin.py",)
    for wrapper in wrappers:
        tree = ast.parse(wrapper.read_text(encoding="utf-8"))
        assert not any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))

    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as directory:
        output = Path(directory)
        BUILDER.build(output)
        entries = (
            output
            / "Glyphs MCP Bridge.glyphsPlugin"
            / "Contents"
            / "Resources"
            / "plugin.py",
            output
            / "Glyphs Curve Inspector.glyphsReporter"
            / "Contents"
            / "Resources"
            / "plugin.py",
        )
        entries += (output / "Glyphs Reference Inspector.glyphsReporter/Contents/Resources/plugin.py",)
        for entry in entries:
            tree = ast.parse(entry.read_text(encoding="utf-8"))
            assert len(
                [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            ) == 1
