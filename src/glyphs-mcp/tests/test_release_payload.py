"""Release signing must include private native dependencies and preserve identities."""
import importlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
release = importlib.import_module("release_payload")


def test_inventory_includes_runtime_libraries_and_excludes_text(tmp_path):
    paths = ["Lean/runtimes/arm64/bin/python3", "Lean/runtimes/x86_64/lib/libpython.dylib",
             "Lean/runtimes/arm64/lib/site-packages/native.so",
             "Lean/Bridge.glyphsPlugin/Contents/MacOS/plugin"]
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xcf\xfa\xed\xfe" + b"fixture")
    (tmp_path / "readme").write_text("not native code")
    (tmp_path / "python").symlink_to(paths[0])
    natives, bundles = release.inventory(tmp_path)
    assert {str(p.relative_to(tmp_path)) for p in natives} == set(paths)
    assert bundles == [tmp_path / "Lean/Bridge.glyphsPlugin"]


def test_inventory_rejects_escape_before_signing(tmp_path):
    (tmp_path / "escape").symlink_to(tmp_path.parent)
    with pytest.raises(ValueError, match="escapes"):
        release.inventory(tmp_path)


def test_bundle_order_is_inside_out(tmp_path):
    outer = tmp_path / "Outer.glyphsPlugin"
    inner = outer / "Contents/Resources/Inner.glyphsReporter"
    inner.mkdir(parents=True)
    assert release.inventory(tmp_path)[1] == [inner, outer]


def test_refresh_updates_signed_and_stapled_component_identities(tmp_path):
    lean = tmp_path / "Lean"
    lean.mkdir()
    manifest = {"bridge": {"bundle": release.BRIDGE, "identity": "old", "codeHash": "old"},
                "companions": [{"id": key, "bundle": name, "identity": "old"}
                               for key, name in release.COMPANIONS.items()],
                "sidecar": {"identity": "old"},
                "runtimes": {a: {"path": "runtimes/" + a, "identity": "old"}
                             for a in ("arm64", "x86_64")}}
    for path in [release.BRIDGE, *release.COMPANIONS.values(), "sidecar", "runtimes/arm64", "runtimes/x86_64"]:
        (lean / path).mkdir(parents=True)
        (lean / path / "code").write_bytes(b"signed bytes")
    (lean / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "payload.json").write_text('{"leanIdentity": "old"}')
    release.refresh_identities(tmp_path)
    release.verify_identities(tmp_path)
    before_hash = json.loads((lean / "manifest.json").read_text())["bridge"]["codeHash"]
    (lean / release.BRIDGE / "CodeResources").write_bytes(b"ticket")
    with pytest.raises(ValueError, match="fingerprint"):
        release.verify_identities(tmp_path)
    release.refresh_identities(tmp_path)
    release.verify_identities(tmp_path)
    signed = json.loads((lean / "manifest.json").read_text())["bridge"]
    assert signed["identity"] != "old"
    assert signed["codeHash"] != before_hash
    assert signed["codeHash"] == release._fingerprint_helper().payload_hash(lean/release.BRIDGE)


def test_component_paths_cannot_be_changed_by_manifest(tmp_path):
    (tmp_path / "Lean").mkdir()
    (tmp_path / "Lean/manifest.json").write_text(json.dumps({"bridge": {"bundle": "../outside"}}))
    with pytest.raises(ValueError, match="bundle"):
        release.refresh_identities(tmp_path)


def test_four_managed_bundles_include_pinned_glyphs3_and_both_companions(tmp_path):
    paths = release.managed_bundles(tmp_path)
    assert len(paths) == 4
    assert paths[0] == tmp_path / "Plugins/Glyphs3/Glyphs MCP.glyphsPlugin"
    assert {p.name for p in paths[1:]} == {release.BRIDGE, *release.COMPANIONS.values()}
