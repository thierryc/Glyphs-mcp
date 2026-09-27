"""Create disposable saved fonts for the installed chat/editor qualification."""
from pathlib import Path
from GlyphsApp import GSFont, GSFontMaster, GSGlyph, GSPath, GSNode
root=Path(__file__).resolve().parents[1]/'build/simple-native-editor-fixtures'
root.mkdir(parents=True,exist_ok=True)
for suffix in ('glyphs','glyphspackage'):
    target=root/('Native Script Editor Test.'+suffix)
    if target.exists():raise RuntimeError('fixture already exists; do not overwrite an open fixture')
    font=GSFont();font.familyName='MCP Native Script Editor Test';font.grid=1
    master=GSFontMaster();master.name='Regular';font.masters.append(master)
    for name in ('A','B'):
        glyph=GSGlyph(name);font.glyphs.append(glyph);layer=glyph.layers[master.id]
        layer.width=500
        for surface in (layer,layer.background):
            surface.setTemporarilyDisableRounding_(True)
            path=GSPath();path.closed=True
            for point in ((10.25,0),(55.5,700.25),(300.25,100.5)):path.nodes.append(GSNode(point))
            surface.shapes.append(path);surface.setTemporarilyDisableRounding_(False)
    font.save(str(target),makeCopy=True)
    print(str(target),master.id,flush=True)
