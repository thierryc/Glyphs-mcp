#!/usr/bin/env python3
"""Bounded Glyphs 4 acceptance for the schema-3 visual diff on disposable packages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src" / part) for part in ("protocol", "sidecar")]

from Foundation import NSPoint, NSURL
from GlyphsApp import (
    CURVE,
    LINE,
    OFFCURVE,
    QCURVE,
    GSAnchor,
    GSComponent,
    GSFont,
    GSGlyph,
    GSLayer,
    GSNode,
    GSPackageBundle,
    GSPath,
)
from glyphs_mcp_sidecar import glyph_diff_worker


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(value for value in root.rglob("*") if value.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load(path: Path):
    value = GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(str(path)), None)
    font = value[0] if isinstance(value, tuple) else value
    assert font is not None, value
    return font


def save(font, path: Path) -> None:
    value = font.saveToURL_type_error_(NSURL.fileURLWithPath_(str(path)), GSPackageBundle, None)
    assert (value[0] if isinstance(value, tuple) else value), value


def path(nodes, *, closed: bool) -> GSPath:
    result = GSPath()
    result.closed = closed
    for x, y, kind in nodes:
        result.nodes.append(GSNode(NSPoint(x, y), kind))
    return result


def layer(font, name: str, master_id: str, *, width: float = 600) -> GSLayer:
    glyph = GSGlyph(name)
    font.glyphs.append(glyph)
    result = GSLayer()
    result.layerId = master_id
    result.associatedMasterId = master_id
    glyph.layers[master_id] = result
    result.width = width
    return result


def add_acceptance_glyphs(font) -> str:
    master_id = str(font.masters[0].id)
    base = layer(font, "previewBase", master_id, width=620)
    base.shapes.append(path([
        (20, 0, LINE), (60, 180, OFFCURVE), (180, 180, OFFCURVE),
        (220, 0, CURVE), (220, 400, LINE), (20, 400, LINE),
    ], closed=True))
    base.shapes.append(path([
        (280, 40, LINE), (330, 160, OFFCURVE), (390, 160, OFFCURVE), (440, 40, CURVE),
    ], closed=False))
    base.anchors.append(GSAnchor("top", NSPoint(120, 420)))

    quadratic = layer(font, "previewQuadratic", master_id, width=500)
    quadratic.shapes.append(path([
        (20, 20, LINE), (150, 260, OFFCURVE), (300, 20, QCURVE),
    ], closed=False))

    component = layer(font, "previewComponent", master_id, width=620)
    component.shapes.append(GSComponent("previewBase"))

    deleted = layer(font, "previewDeleted", master_id, width=300)
    deleted.shapes.append(path([
        (0, 0, LINE), (200, 0, LINE), (200, 200, LINE), (0, 200, LINE),
    ], closed=True))
    return master_id


def glyph_files(package: Path) -> dict[str, Path]:
    result = {}
    for path in package.joinpath("glyphs").glob("*.glyph"):
        name = glyph_diff_worker._glyph_name(path)
        if name:
            result[name] = path
    return result


def compare(before: Path, after: Path, name: str, *, before_present=True, after_present=True):
    before_files, after_files = glyph_files(before), glyph_files(after)
    return glyph_diff_worker.run({
        "beforePackage": str(before) if before_present else None,
        "beforeGlyph": str(before_files[name]) if before_present else None,
        "afterPackage": str(after) if after_present else None,
        "afterGlyph": str(after_files[name]) if after_present else None,
    })


def main() -> None:
    original = ROOT / "GlyphsSDK/GlyphsFileFormat/GlyphsFileFormatv3.glyphspackage"
    original_hash = tree_hash(original)
    with tempfile.TemporaryDirectory(prefix="glyphs-diff-native-") as temporary:
        work = Path(temporary)
        seeded = work / "Seeded.glyphspackage"
        before = work / "Before.glyphspackage"
        after = work / "After.glyphspackage"
        shutil.copytree(original, seeded)
        font = load(seeded)
        master_id = add_acceptance_glyphs(font)
        save(font, seeded)
        shutil.copytree(seeded, before)
        shutil.copytree(seeded, after)

        current = load(after)
        base = current.glyphs["previewBase"].layers[master_id]
        base.paths[0].nodes[3].position = NSPoint(240, 20)
        base.width = 650
        base.anchors["top"].position = NSPoint(140, 440)
        quadratic = current.glyphs["previewQuadratic"].layers[master_id]
        quadratic.paths[0].nodes[1].position = NSPoint(160, 280)
        del current.glyphs["previewDeleted"]
        added = layer(current, "previewAdded", master_id, width=340)
        added.shapes.append(path([
            (20, 0, LINE), (240, 0, LINE), (240, 220, LINE), (20, 220, LINE),
        ], closed=True))
        save(current, after)

        base_diff = compare(before, after, "previewBase")
        base_layer = base_diff["after"]["layers"][0]
        assert any(item["kind"] == 2 for item in base_layer["outline"]), base_layer
        assert base_layer["openOutline"] and not base_layer["warnings"], base_layer
        difference = base_diff["differences"][0]
        assert difference["width"] == [620.0, 650.0], difference
        assert difference["anchors"] and difference["referenceSegments"], difference

        quadratic_diff = compare(before, after, "previewQuadratic")
        quadratic_layer = quadratic_diff["after"]["layers"][0]
        assert any(item["kind"] == 4 for item in quadratic_layer["openOutline"]), quadratic_layer
        assert quadratic_diff["changedLayerIDs"], quadratic_diff

        component_diff = compare(before, after, "previewComponent")
        component_layer = component_diff["after"]["layers"][0]
        assert component_layer["componentOutlines"] and not component_layer["warnings"], component_layer

        added_diff = compare(before, after, "previewAdded", before_present=False)
        deleted_diff = compare(before, after, "previewDeleted", after_present=False)
        assert added_diff["before"]["missingGlyph"] and added_diff["changedLayerIDs"], added_diff
        assert deleted_diff["after"]["missingGlyph"] and deleted_diff["changedLayerIDs"], deleted_diff
        assert base_diff["schemaVersion"] == 3 and base_diff["protocolAPIVersion"] == 1
        assert tree_hash(original) == original_hash

        print(json.dumps({
            "schemaVersion": 3,
            "protocolAPIVersion": 1,
            "cases": ["cubic", "quadratic", "component", "openPath", "anchor",
                      "width", "added", "deleted"],
            "originalFixtureUnchanged": True,
            "scope": "Glyphs 4 native process; disposable package copies only",
        }, sort_keys=True))


if __name__ == "__main__":
    main()
