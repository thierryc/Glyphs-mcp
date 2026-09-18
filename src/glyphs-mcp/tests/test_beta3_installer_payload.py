"""The beta installer payload is Glyphs 4-only and owns a Cursor bundle."""

import importlib.util
import json
from pathlib import Path
import plistlib
import shutil
import sys

import pytest


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
SPEC = importlib.util.spec_from_file_location("beta_payload", REPO / "scripts/build_installer_payload.py")
assert SPEC is not None and SPEC.loader is not None
payload = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(payload)
from build_simple_v2 import _identity


def fixture(root: Path) -> dict:
    lean = root / "Lean"
    bridge = lean / "Glyphs MCP Bridge.glyphsPlugin/Contents"
    bridge.mkdir(parents=True)
    (bridge / "Info.plist").write_bytes(plistlib.dumps({"CFBundleShortVersionString": "2.0.0"}))
    sidecar = lean / "sidecar"
    shutil.copytree(REPO / "src/protocol/glyphs_mcp_protocol", sidecar / "glyphs_mcp_protocol")
    shutil.copytree(REPO / "src/sidecar/glyphs_mcp_sidecar", sidecar / "glyphs_mcp_sidecar")
    reader = {
        "schemaVersion": 3,
        "protocolAPIVersion": 1,
        "workerModule": "glyphs_mcp_sidecar.glyph_diff_worker",
    }
    (lean / "manifest.json").write_text(json.dumps({
        "glyphDiffReader": reader,
        "sidecar": {"glyphDiffReader": reader},
    }))
    installer = root / "Installer"
    installer.mkdir()
    (installer / "install.py").write_text("# fixture\n")
    cursor = root / "AgentPlugins/Cursor/glyphs-mcp"
    (cursor / ".cursor-plugin").mkdir(parents=True)
    (cursor / ".cursor-plugin/plugin.json").write_text(json.dumps({"name": "glyphs-mcp", "version": "2.0.0"}))
    manifest = {
        "schemaVersion": 4,
        "version": "2.0.0",
        "installerBuild": 46,
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


def test_beta_payload_has_only_glyphs4_and_verified_cursor_plugin(tmp_path):
    expected = fixture(tmp_path)
    result = payload.validate_payload(tmp_path, release_version="2.0.0")
    assert result == expected
    assert set(result["targets"]) == {"4"}
    assert "baseline" not in result["targets"]["4"]
    assert result["cursorPlugin"]["path"] == "AgentPlugins/Cursor/glyphs-mcp"
    assert not (tmp_path / "skills-v1").exists()
    assert not (tmp_path / "Plugins/Glyphs3").exists()


def test_beta_payload_rejects_v1_content_and_glyphs3_target(tmp_path):
    manifest = fixture(tmp_path)
    (tmp_path / "skills-v1").mkdir()
    with pytest.raises(ValueError, match="Glyphs 3 content"):
        payload.validate_payload(tmp_path)
    (tmp_path / "skills-v1").rmdir()
    manifest["targets"]["3"] = {"pluginPath": "legacy"}
    (tmp_path / "payload.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unsupported installer payload"):
        payload.validate_payload(tmp_path)


def test_beta_payload_rejects_v1_baseline_metadata(tmp_path):
    manifest = fixture(tmp_path)
    manifest["targets"]["4"]["baseline"] = {"tag": "v1.11.0", "commit": "13ca805"}
    (tmp_path / "payload.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Glyphs 3 baseline metadata"):
        payload.validate_payload(tmp_path)


def test_beta_payload_rejects_tampered_lean_reader_identity(tmp_path):
    fixture(tmp_path)
    geometry = tmp_path / "Lean/sidecar/glyphs_mcp_protocol/geometry.py"
    geometry.write_text(geometry.read_text() + "\n# tampered\n")
    with pytest.raises(ValueError, match="Payload identity mismatch: Lean"):
        payload.validate_payload(tmp_path)


def test_failed_outer_payload_validation_never_replaces_existing_output(tmp_path, monkeypatch):
    import build_simple_v2

    output = tmp_path / "Payload"
    output.mkdir()
    marker = output / "existing-build"
    marker.write_text("keep me")

    def fake_lean_build(destination, *, runtime_root=None):
        destination.mkdir(parents=True)
        return {"projectVersion": "2.0.0", "installerBuild": 46}

    monkeypatch.setattr(build_simple_v2, "build", fake_lean_build)
    monkeypatch.setattr(payload, "validate_payload",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("reader rejected")))
    with pytest.raises(ValueError, match="reader rejected"):
        payload.build_payload(output, allow_outside_worktree=True, runtime_root=tmp_path / "runtime")

    assert marker.read_text() == "keep me"
    assert not (output / "payload.json").exists()


def test_builder_packages_cursor_and_never_copies_v1_payload():
    text = (REPO / "scripts/build_installer_payload.py").read_text()
    assert '"AgentPlugins/Cursor/glyphs-mcp"' in text
    assert "shutil.copytree(CURSOR_PLUGIN" in text
    assert "skills-v1" not in text.split("def build_payload", 1)[1]
    assert "V1_PLUGIN" not in text
