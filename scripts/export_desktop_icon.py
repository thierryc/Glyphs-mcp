#!/usr/bin/env python3
"""Export the authorized Regular-S glyph as a deterministic masked vector PDF."""
import argparse
import hashlib
import json
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.pens.boundsPen import BoundsPen
from glyphsLib.parser import Parser

MASTER = "74EE9863-DD0D-47A4-B98B-F1098734EDA9"
GLYPH = "litsquare.logo.glyphsMCP"
ROOT = Path(__file__).resolve().parents[1]


def draw(nodes, pen):
    # Glyphs node types describe the segment ending at that node. Off-curves
    # before the first on-curve belong to the closing segment.
    first = next(i for i, node in enumerate(nodes) if node[2] != "o")
    ordered = nodes[first:] + nodes[:first] + [nodes[first]]
    pen.moveTo(tuple(ordered[0][:2]))
    controls = []
    for x, y, kind in ordered[1:]:
        point = (x, y)
        if kind == "o":
            controls.append(point)
        elif kind.startswith("q"):
            pen.qCurveTo(*controls, point); controls = []
        elif kind.startswith("c"):
            pen.curveTo(*controls, point); controls = []
        elif kind.startswith("l"):
            assert not controls
            pen.lineTo(point)
        else:
            raise ValueError("Unsupported icon node type: " + kind)
    assert not controls
    pen.closePath()


class PDFPen(BasePen):
    def __init__(self): super().__init__(None); self.commands = []
    def command(self, operator, *points):
        self.commands.append(" ".join(format(number, ".9g") for point in points for number in point) + " " + operator)
    def _moveTo(self, point): self.command("m", point)
    def _lineTo(self, point): self.command("l", point)
    def _curveToOne(self, *points): self.command("c", *points)
    def _closePath(self): self.commands.append("h")


def export(source, destination):
    glyph_path = source / "glyphs/litsquare.logo.glyphsM_C_P_.glyph"
    glyph = Parser().parse(glyph_path.read_text())
    assert glyph["glyphname"] == GLYPH
    layer = next(item for item in glyph["layers"] if item["layerId"] == MASTER)
    bounds = BoundsPen(None)
    paths = []
    for shape in layer["shapes"]:
        assert shape["closed"] == 1 and "nodes" in shape
        pen = PDFPen(); draw(shape["nodes"], pen)
        mask = bool(shape.get("attr", {}).get("mask"))
        paths.append((mask, "\n".join(pen.commands)))
        if not mask: draw(shape["nodes"], bounds)
    x0, y0, x1, y1 = bounds.bounds
    scale = 18 / max(x1 - x0, y1 - y0)
    tx, ty = (18 - scale * (x1 + x0)) / 2, (18 - scale * (y1 + y0)) / 2
    commands = [f"q {scale:.12g} 0 0 {scale:.12g} {tx:.12g} {ty:.12g} cm", "0 g"]
    for i, (mask, path) in enumerate(paths):
        if mask: continue
        commands.append("q")
        for later_mask, later_path in paths[i+1:]:
            if later_mask:
                commands += ["-10000 -10000 20000 20000 re", later_path, "W* n"]
        commands += [path, "f", "Q"]
    commands.append("Q")
    stream = "\n".join(commands).encode("ascii")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 18 18] /Contents 4 0 R /Resources << >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"); offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data)); data.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    offset = len(data)
    data.extend(b"xref\n0 5\n0000000000 65535 f \n")
    for value in offsets[1:]: data.extend(f"{value:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{offset}\n%%EOF\n".encode())
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "GlyphsMCPMenu.pdf").write_bytes(data)
    (destination / "Contents.json").write_text(json.dumps({"images": [{"filename": "GlyphsMCPMenu.pdf", "idiom": "universal"}],
        "info": {"author": "xcode", "version": 1}, "properties": {"preserves-vector-representation": True, "template-rendering-intent": "template"}}, indent=2) + "\n")
    provenance = {"glyph": GLYPH, "master": "Regular-S", "masterId": MASTER,
        "source": "litsquare-symbols/sf-symbols/litsquare-icons.glyphspackage",
        "author": "Thierry Charbonnel / LitSquare", "license": "SIL Open Font License 1.1",
        "repository": "https://github.com/thierryc/litsquare-symbols",
        "glyphSHA256": hashlib.sha256(glyph_path.read_bytes()).hexdigest(),
        "fontInfoSHA256": hashlib.sha256((source / "fontinfo.plist").read_bytes()).hexdigest(),
        "layerSHA256": hashlib.sha256(json.dumps(layer, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "assetSHA256": hashlib.sha256(data).hexdigest(), "positiveContours": sum(not mask for mask, _ in paths),
        "maskContours": sum(mask for mask, _ in paths), "bounds": bounds.bounds}
    (ROOT / "third_party/desktop-icon.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=ROOT / "macos-installer/GlyphsMCPInstaller/Resources/Assets.xcassets/GlyphsMCPMenu.imageset")
    args = parser.parse_args(); export(args.source, args.destination)
