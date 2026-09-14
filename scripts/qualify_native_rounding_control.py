"""Isolate native setter Undo rounding with no MCP modules or plugins loaded."""
import json
from pathlib import Path
from GlyphsApp import GSFont, GSFontMaster, GSGlyph, GSPath, GSNode, LINE
from Foundation import NSPoint, NSUndoManager

font=GSFont()
master=GSFontMaster();font.masters.append(master)
glyph=GSGlyph('nativeRoundingControl');font.glyphs.append(glyph)
layer=glyph.layers[master.id]
path=GSPath();path.closed=False
layer.setTemporarilyDisableRounding_(True)
node=GSNode(NSPoint(47.547,1404),LINE);path.nodes.append(node);layer.shapes.append(path)
layer.setTemporarilyDisableRounding_(False)
before=tuple(node.position)
manager=NSUndoManager.alloc().init();manager.setGroupsByEvent_(False)
manager.beginUndoGrouping()
manager.prepareWithInvocationTarget_(node).setPosition_(NSPoint(*before))
node.position=NSPoint(49,1404)
manager.endUndoGrouping()
manager.undo()
after=tuple(node.position)
assert before==(47.547,1404) and after==(48.0,1404), (before,after)
result={'plugins':'disabled','importsMCP':False,'before':before,'nativeUndo':after,
        'reproduced':True,'explanation':'Native GSNode.setPosition_ rounds fractional coordinates while rounding is enabled.'}
(Path(__file__).resolve().parents[1]/'build/native-rounding-control.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
