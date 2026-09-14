"""Isolated native benefit/integration gate; run through glyphs-cli, plugins off."""

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
for part in ('sidecar', 'protocol', 'bridge'):
    sys.path.insert(0, str(ROOT / 'src' / part))

from Foundation import NSPoint
from GlyphsApp import GSFont, GSFontMaster, GSGlyph, GSLayer, GSPath, GSNode, GSAnchor, LINE
from glyphs_mcp_sidecar import spacing, spacing_job, native_worker
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore


def main():
    font = native_worker._load_font(ROOT/'src/glyphs-mcp/tests/fixtures/headless-preview-minimal.glyphs')
    font.glyphs = []
    master = font.masters[0]
    master.xHeight = 500; master.capHeight = 700
    mid = str(master.id)

    def add(name, points, width):
        glyph = GSGlyph(name); font.glyphs.append(glyph)
        layer = GSLayer(); layer.layerId = mid; layer.associatedMasterId = mid
        glyph.layers[mid] = layer
        path = GSPath(); path.closed = True
        for xy in points: path.nodes.append(GSNode(NSPoint(*xy), LINE))
        layer.shapes.append(path)
        layer.setTemporarilyDisableRounding_(True); layer.width = width; layer.setTemporarilyDisableRounding_(False)
        return glyph, layer

    add('H', [(0,0),(600,0),(600,700),(0,700)], 600)
    add('x', [(0,0),(600,0),(600,500),(0,500)], 600)
    diagonal = [(450,0),(550,0),(1000,700),(0,700)]
    benefits = []
    for name in ('V','W','Y'):
        glyph, layer = add(name, diagonal, 1000)
        old = spacing.suggest(font,glyph,layer,spacing.validate_options({'reference':'x'}))
        new = spacing.suggest(font,glyph,layer,spacing.validate_options({}))
        assert min(old['after']['lsb'],old['after']['rsb']) < -50, old
        assert min(new['after']['lsb'],new['after']['rsb']) > -50, new
        assert new['selectedReference'] == 'H'
        benefits.append({'glyph':name,'lowercase':old['after'],'uppercase':new['after']})
    for index,name in enumerate(spacing.FIGURES):
        add(name,[(100,0),(400,0),(400,700),(100,700)],600.125+index/10)
    fractional_glyph,fractional_layer=add('fractional', [(10.125,0.25),(410.625,0.25),(410.625,700.75),(10.125,700.75)], 600.875)
    boundary_checks=[]
    for translated in (False,True):
        measured=spacing.exact_copy(fractional_layer)
        if translated:measured.applyTransform((1,0,0,1,23.375,17.625))
        for step in (5,1,.5):
            row=spacing.suggest(font,fractional_glyph,measured,spacing.validate_options({'reference':'*','area':400.125,'sampleStep':step}))
            assert all(abs(row['after'][key]-80.025)<1e-9 for key in ('lsb','rsb')),row
            boundary_checks.append(dict(translated=translated,step=step,after=row['after']))
    mark, mark_layer = add('acutecomb',[(0,0),(40,0),(40,80),(0,80)],0)
    mark.category = 'Mark'
    active = font.glyphs['V'].layers[mid]
    active.anchors.append(GSAnchor('top',NSPoint(500.125,710.25)))
    directory = Path(tempfile.mkdtemp(prefix='glyphs-spacing-native-'))
    # The thin wrapper supplies document state, not an alternate geometry model.
    wrapper = SimpleNamespace(glyphs=font.glyphs, masters=font.masters, familyName='Native spacing fixture',
                              filepath=str(directory/'Fixture.glyphs'),
                              parent=SimpleNamespace(isDocumentEdited=lambda:False,changeCount=lambda:0,undoManager=lambda:None))
    adapter = GlyphsAdapter(SimpleNamespace(fonts=[wrapper])); document = adapter.list_documents()[0]
    original_loader = native_worker._load_font
    native_worker._load_font = lambda _: font
    try:
        patch = native_worker.build_patch({'request':{'kind':'spacing','options':{'area':400.125}},
            'source':wrapper.filepath,'sourceHash':'sha256:'+'a'*64,'jobId':'job_native_spacing',
            'document':document,'output':str(directory/'patch.json')})
    finally:
        native_worker._load_font = original_loader
    baseline = {(str(g.name),str(l.layerId)):(float(l.width),spacing_job.layer_hash(l)) for g in font.glyphs for l in g.layers}
    queue=[]; bridge=BridgeCore(adapter,schedule=queue.append)
    bridge.begin_apply(patch)
    while queue: queue.pop(0)()
    assert bridge.operation(patch['jobId'])['status']=='applied',bridge.operation(patch['jobId'])
    report=json.loads((directory/'report.json').read_text())
    assert not any(row['status']=='unavailable' for row in report['layers']), report
    fractional=0
    for row in report['layers']:
        layer=font.glyphs[row['glyph']].layers[row['layer']]
        if row['status']=='suggested':
            xs=[float(node.position.x) for path in layer.paths for node in path.nodes]
            x,w=min(xs),max(xs)-min(xs)
            actual={'lsb':x,'rsb':float(layer.width)-x-w,'width':float(layer.width)}
            assert all(abs(actual[k]-row['after'][k])<1e-8 for k in actual),(row,actual)
            fractional+=not float(x).is_integer()

    assert fractional
    assert float(mark_layer.width)==0
    for name in spacing.FIGURES:
        assert float(font.glyphs[name].layers[mid].width)==baseline[(name,mid)][0]
    bridge.discard(patch['jobId'])
    while queue: queue.pop(0)()
    assert bridge.operation(patch['jobId'])['status']=='discarded',bridge.operation(patch['jobId'])
    assert all((float(l.width),spacing_job.layer_hash(l))==baseline[(str(g.name),str(l.layerId))] for g in font.glyphs for l in g.layers)
    result={'benefits':benefits,'boundaryChecks':boundary_checks,'fractionalBearings':fractional,'changes':len(patch['changes']),
            'tabularWidthsPreserved':True,'zeroWidthMarksPreserved':True,'nativeBridgeApplyAndDiscard':True,
            'exactGeometryAndWidthsRestored':True,'scope':'isolated native process; editor acceptance is separate'}
    (ROOT/'build/spacing-native-benefit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__': main()
