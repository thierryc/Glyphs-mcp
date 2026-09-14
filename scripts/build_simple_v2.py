#!/usr/bin/env python3
"""Assemble the lean sidecar and bridge without importing the old v2 runtime."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import plistlib
import shutil
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
BRIDGE = REPO / "src" / "bridge"
PROTOCOL = REPO / "src" / "protocol" / "glyphs_mcp_protocol"
SIDECAR = REPO / "src" / "sidecar" / "glyphs_mcp_sidecar"
BUNDLE = BRIDGE / "bundle" / "Glyphs MCP Bridge.glyphsPlugin"
COMPANIONS = REPO / "src" / "companions"
COMPANION_SDK = COMPANIONS / "sdk" / "glyphs_mcp_companions.py"
CURVE = COMPANIONS / "curve-inspector"


def _ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if name == "__pycache__" or name.endswith(".pyc")}


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=_ignore, symlinks=True)


def _identity(root: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(
        (candidate for candidate in root.rglob("*") if candidate.is_file()),
        key=lambda candidate: candidate.relative_to(root).as_posix(),
    ):
        relative = item.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with item.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _fingerprint_helper():
    # Build/release only: the standalone installer imports _identity without this dependency.
    spec = importlib.util.spec_from_file_location("payload_fingerprint", PROTOCOL / "identity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _set_version(bundle, version):
    path = bundle / "Contents/Info.plist"
    data = plistlib.loads(path.read_bytes())
    data.update(CFBundleShortVersionString=version, CFBundleVersion=version)
    path.write_bytes(plistlib.dumps(data, sort_keys=True))


def build(output: Path, *, runtime_root: Path | None = None) -> dict:
    # The packaged installer imports only _identity; release configuration is build-time only.
    from desktop_release_identity import load as release_identity
    release = release_identity(REPO)
    fingerprints = _fingerprint_helper()
    metadata = {key: release[key] for key in fingerprints.RELEASE_FIELDS}
    output = output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    bundle = output / BUNDLE.name
    _copy_tree(BUNDLE, bundle)
    resources = bundle / "Contents" / "Resources"
    _copy_tree(BRIDGE / "glyphs_mcp_bridge", resources / "glyphs_mcp_bridge")
    layout_path = resources / "glyphs_mcp_bridge/server_panel.json"
    layout = json.loads(layout_path.read_text())
    layout["projectVersion"] = json.loads((REPO / "plugins/glyphs-mcp/.claude-plugin/plugin.json").read_text())["version"]
    layout["releaseLabel"] = release["label"]
    layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n")
    _copy_tree(PROTOCOL, resources / "glyphs_mcp_protocol")
    shutil.copy2(COMPANION_SDK, resources / COMPANION_SDK.name)
    shutil.copy2(BRIDGE / "glyphs_mcp_bridge" / "plugin.py", resources / "plugin.py")
    with (resources / "plugin.py").open("a") as stream:
        stream.write("\nfrom glyphs_mcp_bridge.server_panel import GlyphsMCPServerPlugin\n")
    sidecar = output / "sidecar"
    sidecar.mkdir()
    _copy_tree(SIDECAR, sidecar / "glyphs_mcp_sidecar")
    _copy_tree(PROTOCOL, sidecar / "glyphs_mcp_protocol")
    _copy_tree(CURVE / "curve_core", sidecar / "curve_core")
    for script, module in (("run", "server"), ("control", "control"), ("proxy", "proxy")):
        (sidecar / (script + ".py")).write_text(
            "import os, sys\nsys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))\n"
            "from glyphs_mcp_sidecar." + module + " import main\nraise SystemExit(main())\n",
            encoding="utf-8",
        )
    companion_values = []
    project_version = release["version"]
    if layout["projectVersion"] != project_version:
        raise ValueError("Plugin and product versions disagree")
    for identifier, title, package_name, core_name in (
        ("curve-inspector", "Glyphs Curve Inspector", "glyphs_curve_inspector", "curve_core"),
        ("reference-inspector", "Glyphs Reference Inspector", "glyphs_reference_inspector", "reference_core"),
    ):
        root = COMPANIONS / identifier
        source = root / "bundle" / (title + ".glyphsReporter")
        target = output / source.name
        _copy_tree(source, target)
        companion_resources = target / "Contents" / "Resources"
        package = root / package_name
        _copy_tree(package, companion_resources / package.name)
        shutil.copy2(COMPANION_SDK, companion_resources / COMPANION_SDK.name)
        _copy_tree(root / core_name, companion_resources / core_name)
        if identifier == "reference-inspector":
            _copy_tree(PROTOCOL, companion_resources / "glyphs_mcp_protocol")
        shutil.copy2(package / "plugin.py", companion_resources / "plugin.py")
        _set_version(target, project_version)
        companion_values.append(
            {"id": identifier, "bundle": source.name, "identity": _identity(target)}
        )
    _set_version(bundle, project_version)
    for release_file in (
        resources / fingerprints.RELEASE_FILE,
        sidecar / fingerprints.RELEASE_FILE,
    ):
        release_file.write_text(
            json.dumps(metadata, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schemaVersion": 2,
        "projectVersion": project_version,
        "installerBuild": release["installerBuild"],
        "releaseChannel": release["channel"],
        "releaseVersion": release["releaseVersion"],
        "version": project_version,
        "release": metadata,
        "protocol": 1,
        "tools": [
            "get_status",
            "list_documents",
            "read_entities",
            "start_job",
            "get_job",
            "apply_job",
            "discard_job",
        ],
        "bridge": {"bundle": BUNDLE.name, "identity": _identity(bundle),
                   "codeHash": fingerprints.payload_hash(bundle), "release": metadata},
        "sidecar": {"identity": _identity(sidecar),
                    "codeHash": fingerprints.payload_hash(sidecar), "release": metadata},
        "companions": companion_values,
    }
    if runtime_root is not None:
        manifest["runtimes"] = {}
        for architecture in ("arm64", "x86_64"):
            source = runtime_root / architecture
            metadata = json.loads(source.with_suffix(".json").read_text())
            if _identity(source) != metadata["identity"]:
                raise ValueError("Private runtime identity mismatch: " + architecture)
            target = output / "runtimes" / architecture
            target.parent.mkdir(exist_ok=True)
            _copy_tree(source, target)
            manifest["runtimes"][architecture] = {key: metadata[key] for key in
                ("identity", "pythonVersion", "python", "glyphsCLI")}
            manifest["runtimes"][architecture]["path"] = "runtimes/" + architecture
            manifest["runtimes"][architecture]["glyphsCLIVersion"] = "0.6.1"
            manifest["runtimes"][architecture]["dependencyLockSHA256"] = hashlib.sha256((REPO / "third_party" / ("lean-runtime-" + architecture + ".lock")).read_bytes()).hexdigest()
    manifest["components"] = {"mcp": {"requires": ["runtime", "sidecar", "bridge"]},
                              "curve-inspector": {"requires": []}, "reference-inspector": {"requires": ["runtime"]}}
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO / "build" / "simple-v2")
    args = parser.parse_args()
    print(json.dumps(build(args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
