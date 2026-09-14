"""Real NSUndoManager regression for fractional coordinates in three masters."""
import json
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import uuid4

from qualify_simple_v2_slant_native import ROOT, snapshot, native_worker, coordinates, GlyphsAdapter
from GlyphsApp import GSGlyph, GSLayer, GSPath, GSNode, GSAnchor, GSHint, LINE, STEM
from Foundation import NSPoint, NSUndoManager
from glyphs_mcp_bridge.native_undo import write_value


def main():
    font = native_worker._load_font(ROOT / 'src/glyphs-mcp/tests/fixtures/headless-preview-minimal.glyphs')
    for glyph in list(font.glyphs): del font.glyphs[glyph.name]
    for index in range(2):
        master = font.masters[0].copy()
        master.id = str(uuid4())
        master.name = 'History ' + str(index + 2)
        font.masters.append(master)
    glyph = GSGlyph('historyTest')
    font.glyphs.append(glyph)
    layers, changes = [], []
    font.grid = 1
    for master in font.masters:
        layer = glyph.layers[master.id]
        layer.setTemporarilyDisableRounding_(True)
        layer.width = 600.125
        path = GSPath()
        path.closed = True
        for index, (x, y) in enumerate(((.125, .25), (100.125, .25), (100.125, 800.25), (.125, 800.25))):
            node = GSNode(NSPoint(x, y), LINE)
            node.userData['logicalNode'] = index
            path.nodes.append(node)
        layer.shapes.append(path)
        layer.anchors.append(GSAnchor('top', NSPoint(50.125, 800.25)))
        hint = GSHint()
        hint.type = STEM
        hint.originNode, hint.targetNode = path.nodes[0], path.nodes[1]
        layer.hints.append(hint)
        layer.setTemporarilyDisableRounding_(False)
        change = dict(kind='coordinates', nodes=[[0, i] for i in range(4)], anchors=['top'],
                      components=[], topologyHash=coordinates.signature(layer))
        change['before'] = coordinates.read(layer, change)
        change['after'] = [[x + y * .2134567, y + .375] for x, y in change['before']]
        layers.append(layer)
        changes.append(change)
    baseline = [snapshot(layer) for layer in layers]
    manager = NSUndoManager.alloc().init()
    manager.setGroupsByEvent_(False)
    manager.beginUndoGrouping()
    for layer, change in zip(layers, changes):
        write_value(manager, layer, change, change['after'], coordinates.read_state, GlyphsAdapter._write_exact)
    manager.endUndoGrouping()
    for direction, action in [('after', manager.undo), ('before', manager.redo), ('after', manager.undo), ('before', None)]:
        for layer, change, before in zip(layers, changes, baseline):
            assert coordinates.read(layer, change) == change[direction]
            after = snapshot(layer)
            for field in ('width', 'topology', 'metadata', 'hints'):
                assert after[field] == before[field], (direction, field)
            assert not layer.temporarilyDisableRounding()
        assert manager.isUndoRegistrationEnabled() and font.grid == 1
        if action: action()
    result = dict(passed=True, masters=len(layers), exactUndoRedo=True, preserved=['width', 'topology', 'metadata', 'hints', 'object identity', 'rounding flags', 'grid', 'Undo registration'])
    (ROOT / 'build/exact-history-native.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__': main()
