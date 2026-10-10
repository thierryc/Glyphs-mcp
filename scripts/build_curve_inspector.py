#!/usr/bin/env python3
"""Build Curve Inspector and its skill without rebuilding/installing MCP."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import plistlib
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/companions/curve-inspector"
sys.path.insert(0, str(SOURCE))
from curve_repair.provenance import record, validate


def copy(source, target):
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store"))


def build(output):
    output = Path(output).resolve()
    if output == SOURCE or SOURCE in output.parents: raise ValueError("Build output cannot replace companion source")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".curve-inspector-build-", dir=output.parent) as temporary:
        stage = Path(temporary) / "candidate"; stage.mkdir()
        bundle = stage / "Glyphs Curve Inspector.glyphsReporter"
        copy(SOURCE / "bundle" / bundle.name, bundle)
        resources = bundle / "Contents/Resources"
        for package in ("glyphs_curve_inspector", "curve_core", "curve_repair"):
            copy(SOURCE / package, resources / package)
        shutil.copy2(ROOT / "src/companions/sdk/glyphs_mcp_companions.py", resources / "glyphs_mcp_companions.py")
        # Glyphs/SDK validation expects the principal class in the main file.
        # Its imports are absolute; the package initializer defines no Reporter.
        shutil.copy2(SOURCE / "glyphs_curve_inspector/plugin.py", resources / "plugin.py")
        skill = stage / "skills/glyphs-curve-repair"
        copy(SOURCE / "skill/glyphs-curve-repair", skill)
        assets = skill / "assets"; assets.mkdir()
        for package in ("curve_core", "curve_repair"): copy(SOURCE / package, assets / package)
        expected = record(SOURCE)
        validate(resources, expected); validate(assets, expected)
        for base in (resources, assets):
            (base / "curve-repair-engine.json").write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
        identity = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
        manifest = {"schemaVersion": 1, "bundle": bundle.name,
                    "bundleIdentifier": identity["CFBundleIdentifier"],
                    "pluginVersion": identity["CFBundleShortVersionString"],
                    "description": "Inspect & Repair", "engine": expected,
                    "nativeQualification": "scope-specific native records in source; compare engine and installed bundle hashes"}
        (stage / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        previous = Path(temporary) / "previous"
        if output.exists(): output.rename(previous)
        try: stage.rename(output)
        except BaseException:
            if previous.exists() and not output.exists(): previous.rename(output)
            raise
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/curve-inspector-candidate")
    args = parser.parse_args()
    result = build(args.output)
    print(json.dumps({"output": str(args.output.resolve()), "pluginVersion": result["pluginVersion"],
                      "engineDigest": result["engine"]["sourceDigest"]}, sort_keys=True))
