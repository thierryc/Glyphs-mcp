"""Beta-3 installer payload is Glyphs 4-only and owns a Cursor bundle."""

import importlib.util
import json
from pathlib import Path
import plistlib
import sys

import pytest


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
SPEC = importlib.util.spec_from_file_location("beta3_payload", REPO / "scripts/build_installer_payload.py")
assert SPEC is not None and SPEC.loader is not None
payload = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(payload)
from build_simple_v2 import _identity


def fixture(root: Path) -> dict:
    lean = root / "Lean"
    bridge = lean / "Glyphs MCP Bridge.glyphsPlugin/Contents"
    bridge.mkdir(parents=True)
    (bridge / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": "2.0.0"}))
    installer = root / "Installer"
    installer.mkdir()
    (installer / "install.py").write_text("# fixture\n")
    cursor = root / "AgentPlugins/Cursor/glyphs-mcp"
    (cursor / ".cursor-plugin").mkdir(parents=True)
    (cursor / ".cursor-plugin/plugin.json").write_text(json.dumps({"name": "glyphs-mcp", "version": "2.0.0"}))
    manifest = {
        "schemaVersion": 4,
        "version": "2.0.0",
        "installerBuild": 45,
        "leanIdentity": _identity(lean),
        "installerIdentity": _identity(installer),
        "cursorPlugin": {
            "path": "AgentPlugins/Cursor/glyphs-mcp",
            "version": "2.0.0",
            "identity": _identity(cursor),
        },
        "targets": {
            "4": {
                "pluginPath": "Lean/Glyphs MCP Bridge.glyphsPlugin",
                "pluginVersion": "2.0.0",
            }
        },
    }
    (root / "payload.json").write_text(json.dumps(manifest))
    return manifest


def test_beta3_payload_has_only_glyphs4_and_verified_cursor_plugin(tmp_path):
    expected = fixture(tmp_path)
    result = payload.validate_payload(tmp_path, release_version="2.0.0")
    assert result == expected
    assert set(result["targets"]) == {"4"}
    assert "baseline" not in result["targets"]["4"]
    assert result["cursorPlugin"]["path"] == "AgentPlugins/Cursor/glyphs-mcp"
    assert not (tmp_path / "skills-v1").exists()
    assert not (tmp_path / "Plugins/Glyphs3").exists()


def test_beta3_payload_rejects_v1_content_and_glyphs3_target(tmp_path):
    manifest = fixture(tmp_path)
    (tmp_path / "skills-v1").mkdir()
    with pytest.raises(ValueError, match="Glyphs 3 content"):
        payload.validate_payload(tmp_path)
    (tmp_path / "skills-v1").rmdir()
    manifest["targets"]["3"] = {"pluginPath": "legacy"}
    (tmp_path / "payload.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unsupported installer payload"):
        payload.validate_payload(tmp_path)


def test_beta3_payload_rejects_v1_baseline_metadata(tmp_path):
    manifest = fixture(tmp_path)
    manifest["targets"]["4"]["baseline"] = {"tag": "v1.11.0", "commit": "13ca805"}
    (tmp_path / "payload.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Glyphs 3 baseline metadata"):
        payload.validate_payload(tmp_path)


def test_builder_packages_cursor_and_never_copies_v1_payload():
    text = (REPO / "scripts/build_installer_payload.py").read_text()
    assert '"AgentPlugins/Cursor/glyphs-mcp"' in text
    assert "shutil.copytree(CURSOR_PLUGIN" in text
    assert "skills-v1" not in text.split("def build_payload", 1)[1]
    assert "V1_PLUGIN" not in text
