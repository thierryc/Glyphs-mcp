"""Qualify closed compilation and export in the exact Glyphs 4 worker runtime."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
for part in ("protocol", "bridge", "sidecar"):
    sys.path.insert(0, str(ROOT / "src" / part))

from GlyphsApp import GSFeature, GSFont, GSInstance, Glyphs

from glyphs_mcp_protocol.compile_export import validate_export_options
from glyphs_mcp_sidecar import feature_compile_job, font_export_job


FIXTURE = ROOT / "GlyphsSDK/ObjectWrapper/UnitTest/Glyphs Unit Test Sans.glyphs"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value(owner, name, default=None):
    item = getattr(owner, name, default)
    return item() if callable(item) else item


def compile_probe():
    font = GSFont(str(FIXTURE))
    report = feature_compile_job.prepare(
        font, {"kind": "feature_compile", "options": {"mode": "saved"}}
    )
    assert report["beforeHash"] == report["afterHash"]
    assert isinstance(report["success"], bool) and isinstance(report["errors"], list)
    return report


def export_probe():
    before = digest(FIXTURE)
    font = GSFont(str(FIXTURE))
    font.features.append(GSFeature("liga", "sub a n by a.sc;"))
    compiled = font.compileFeatures()
    assert isinstance(compiled, tuple) and compiled[0] is True, compiled
    static = next(item for item in list(font.instances) if value(item, "type") == 0)
    options = validate_export_options({
        "instanceId": str(value(static, "id")),
        "format": "ttf",
        "containers": ["plain", "woff", "woff2"],
        "generation": {"useProductionNames": False},
        "verification": {"shapingCases": [{
            "text": "an", "feature": "liga", "expect": "different",
            "controlText": "na",
        }]},
    })
    with tempfile.TemporaryDirectory(prefix="glyphs-compile-export-") as temporary:
        root = Path(temporary)
        manifest, report = font_export_job.prepare(
            font, {"kind": "font_export", "options": options}, root
        )
        assert report["success"] is True
        assert {item["container"] for item in manifest["files"]} == {
            "plain", "woff", "woff2"
        }
        static_manifest = manifest

    variable = GSInstance(type=1)
    variable.name = "Qualification Variable"
    variable.active = True
    font.instances.append(variable)
    variable_options = validate_export_options({
        "instanceId": str(value(variable, "id")),
        "format": "ttf",
        "containers": ["plain"],
    })
    with tempfile.TemporaryDirectory(prefix="glyphs-variable-export-") as temporary:
        variable_manifest, variable_report = font_export_job.prepare(
            font, {"kind": "font_export", "options": variable_options}, Path(temporary)
        )
        assert variable_report["instanceType"] == "variable"
        assert variable_report["verification"]["tables"] is True
    assert digest(FIXTURE) == before
    return {
        "static": static_manifest,
        "variable": variable_manifest,
        "sourceUnchanged": True,
    }


def main():
    print(json.dumps({
        "glyphsVersion": str(Glyphs.versionString),
        "glyphsBuild": str(Glyphs.buildNumber),
        "compile": compile_probe(),
        "export": export_probe(),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
