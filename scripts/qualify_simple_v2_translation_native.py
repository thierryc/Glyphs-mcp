"""Native foreground translation/history/recovery with preserved decorations."""
import json
import objc
from pathlib import Path
from types import SimpleNamespace as NS

from qualify_simple_v2_slant_native import ROOT, native_worker, GlyphsAdapter, coordinates
from GlyphsApp import GSGlyph, GSPath, GSNode, GSAnchor, GSGuide, GSBackgroundImage, GSComponent, LINE
from Foundation import NSPoint, NSUndoManager
from glyphs_mcp_bridge.native_undo import write_value
from glyphs_mcp_bridge.core import BridgeCore
from glyphs_mcp_sidecar import spacing_job


def main():
    font = native_worker._load_font(ROOT / 'src/glyphs-mcp/tests/fixtures/headless-preview-minimal.glyphs')
    master = font.masters[0]
    master.xHeight, master.capHeight = 500, 700
    base = GSGlyph('translationBase'); font.glyphs.append(base)
    base_layer = base.layers[master.id]
    path = GSPath(); path.closed = True
    for xy in ((0, 0), (100, 0), (100, 700), (0, 700)):
        path.nodes.append(GSNode(NSPoint(*xy), LINE))
    base_layer.shapes.append(path)
    glyph = GSGlyph('translationSubject'); font.glyphs.append(glyph)
    layer = glyph.layers[master.id]
    layer.setTemporarilyDisableRounding_(True)
    layer.shapes.append(path.copy())
    component = GSComponent(base.name); component.automaticAlignment = False
    component.transform = (.75, 0, 0, 1.25, 150.125, 20.25)
    layer.shapes.append(component)
    layer.anchors.append(GSAnchor('top', NSPoint(50.125, 710.25)))
    layer.guides.append(GSGuide(NSPoint(22.125, -19.25), 12.5, 'Keep guide'))
    layer.backgroundImage = GSBackgroundImage()
    layer.backgroundImage.position = NSPoint(15.125, -27.25)
    layer.width = 600.125
    layer.setTemporarilyDisableRounding_(False)
    font.grid = 1

    def decorations():
        return (tuple(layer.backgroundImage.transform),
                [(tuple(g.position), g.angle, g.name) for g in layer.guides],
                tuple(component.transform)[:4], layer.width,
                tuple(int(objc.pyobjc_id(n)) for p in layer.paths for n in p.nodes))

    before_decorations = decorations()
    change = dict(kind='translate', glyph=glyph.name, layer=str(master.id), dx=.375, dy=-.125)
    before = coordinates.read_state(layer, change)
    wanted = [(x + change['dx'], y + change['dy']) for x, y in before]
    manager = NSUndoManager.alloc().init(); manager.setGroupsByEvent_(False)
    manager.beginUndoGrouping()
    write_value(manager, layer, change, wanted, coordinates.read_state, GlyphsAdapter._write_exact)
    manager.endUndoGrouping()
    for expected, action in ((wanted, manager.undo), (before, manager.redo),
                             (wanted, manager.undo), (before, None)):
        assert coordinates.read_state(layer, change) == expected
        assert decorations() == before_decorations
        assert font.grid == 1 and not layer.temporarilyDisableRounding()
        assert manager.isUndoRegistrationEnabled()
        if action: action()

    wrapper = NS(glyphs=font.glyphs, masters=font.masters, familyName='Translation fixture',
                 filepath='/tmp/Translation-Native.glyphs',
                 parent=NS(isDocumentEdited=lambda: False, changeCount=lambda: 0, undoManager=lambda: None))
    adapter = GlyphsAdapter(NS(fonts=[wrapper])); document = adapter.list_documents()[0]
    start_hash = adapter._outline_hash(layer)
    shifted_hash = spacing_job.layer_hash(layer, dx=change['dx'], dy=change['dy'])
    request = dict(version=1, jobId='native-translation', documentId=document['id'],
                   sourcePath=document['path'], sourceHash='sha256:' + 'a' * 64, generation=0,
                   summary='Native translation', changes=[dict(change, beforeHash=start_hash, afterHash=shifted_hash)])
    queue = []; core = BridgeCore(adapter, schedule=queue.append, chunk_limit=1)
    core.begin_apply(request)
    while queue: queue.pop(0)()
    assert core.operation(request['jobId'])['status'] == 'applied'
    assert coordinates.read_state(layer, change) == wanted and decorations() == before_decorations
    core.discard(request['jobId'])
    while queue: queue.pop(0)()
    assert core.operation(request['jobId'])['status'] == 'discarded'
    assert coordinates.read_state(layer, change) == before and decorations() == before_decorations

    request['jobId'] = 'native-translation-recovery'
    request['changes'].append(dict(kind='set', glyph=glyph.name, layer=str(master.id),
                                   field='width', before=-1, after=1))
    core.begin_apply(request)
    while queue: queue.pop(0)()
    failed = core.operation(request['jobId'])
    assert failed['status'] == 'failed' and failed['error']['details']['recovery']['complete']
    assert coordinates.read_state(layer, change) == before and decorations() == before_decorations
    assert font.grid == 1 and not layer.temporarilyDisableRounding()
    result = dict(passed=True, fractionalTranslation=True, nativeUndoRedo=True,
                  exactDiscard=True, conflictRecovery=True, decorationsPreserved=True,
                  componentLinearTransformPreserved=True, gridAndRoundingPreserved=True)
    (ROOT / 'build/translation-native-acceptance.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__': main()
