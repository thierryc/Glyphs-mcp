"""Selection projection, native identity, bounds and unavailable-evidence contracts."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
for part in ('protocol', 'bridge'):
    sys.path.insert(0, str(ROOT/'src'/part))
from glyphs_mcp_bridge.core import BridgeError
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_protocol.reads import READ_CAPABILITIES

SUMMARY = ['glyph', 'layer', *GlyphsAdapter.SELECTION_COUNTS]

class Node:
    def __init__(self, parent, index, kind='line'):
        self.parent, self.index, self.type = parent, index, kind
        self.position = NS(x=index + .125, y=-index - .375)
        self.smooth = index % 2 == 1

class Anchor: pass
class Component: pass
class Guide: pass

@pytest.fixture(autouse=True)
def native_types(monkeypatch):
    monkeypatch.setitem(sys.modules, 'GlyphsApp', NS(GSNode=Node, GSAnchor=Anchor,
                                                   GSComponent=Component, GSGuide=Guide))

def setup(count=3):
    layer = NS(layerId='opaque-layer', parent=NS(name='mixed'), selection=[], paths=[])
    for size in (count, 3):
        path = NS(parent=layer, nodes=[])
        path.nodes = [Node(path, i, 'offcurve' if i % 3 == 1 else 'line') for i in range(size)]
        layer.paths.append(path)
    layer.shapes = [Component(), layer.paths[0], Component(), layer.paths[1]]
    layer.selection = list(layer.paths[0].nodes)
    font = NS(currentTab=NS(activeLayer=layer), parent=NS(isDocumentEdited=True))
    adapter = GlyphsAdapter(NS(fonts=[font]))
    doc = adapter._id(font)
    def read(fields=SUMMARY, selector=None, entities=None):
        return adapter.read_entities(doc, entities or [selector or {'kind':'selection'}], fields)[0]['values']
    return layer, font, read

def test_native_class_counts_and_requested_fields():
    layer, _, read = setup()
    layer.selection += [Anchor(), Component(), Guide(), NS(position=(1, 2))]
    assert read() == dict(glyph='mixed', layer='opaque-layer', selectedNodeCount=3,
        selectedAnchorCount=1, selectedComponentCount=1, selectedGuideCount=1, selectedOtherCount=1)
    for key, value in read().items():
        assert read([key]) == {key:value}
    assert 'nodes' not in read()
    assert 'selection.context.v1' in READ_CAPABILITIES

@pytest.mark.parametrize('cls,field', [(Anchor,'selectedAnchorCount'), (Component,'selectedComponentCount'),
                                       (Guide,'selectedGuideCount'), (object,'selectedOtherCount')])
def test_non_node_selection(cls, field):
    layer, _, read = setup()
    layer.selection = [cls()]
    result = read(SUMMARY+['nodes'])
    assert result[field] == 1 and result['selectedNodeCount'] == 0
    assert result['nodes'] == dict(total=0, returned=0, limit=64, complete=True, items=[])

def test_empty_and_no_edit_view_distinct_even_for_nodes_only():
    layer, font, read = setup(0)
    assert read(['glyph','layer','nodes']) == dict(glyph='mixed',layer='opaque-layer',
        nodes=dict(total=0,returned=0,limit=64,complete=True,items=[]))
    font.currentTab = None
    assert read(SUMMARY+['nodes']) == dict(glyph=None,layer=None,nodes=None,
        **dict.fromkeys(GlyphsAdapter.SELECTION_COUNTS,0))
    assert read(['nodes']) == {'nodes':None}

def test_details_use_path_only_and_full_node_indices_in_native_selection_order():
    layer, _, read = setup()
    layer.selection = [layer.paths[1].nodes[2], Anchor(), layer.paths[0].nodes[1]]
    assert read(['nodes']) == {'nodes':dict(total=2, returned=2, limit=64, complete=True, items=[
        dict(x=2.125,y=-2.375,type='line',smooth=False,pathIndex=1,nodeIndex=2),
        dict(x=1.125,y=-1.375,type='offcurve',smooth=True,pathIndex=0,nodeIndex=1)])}

@pytest.mark.parametrize('count', [0,3,63,64,65,255,256,257])
@pytest.mark.parametrize('limit', [1,32,64,256])
def test_detail_limits_are_exact_with_interspersed_objects(count, limit):
    layer, _, read = setup(count)
    layer.selection = [x for node in layer.selection for x in (node, Anchor())]
    selected = list(layer.selection)
    values = read(SUMMARY+['nodes'], {'kind':'selection','nodeLimit':limit})
    result = values['nodes']
    assert result['total'] == values['selectedNodeCount'] == count
    assert values['selectedAnchorCount'] == count
    assert result['returned'] == len(result['items']) == min(count,limit)
    assert result['complete'] is (count <= limit)
    assert result['limit'] == limit
    assert [item['nodeIndex'] for item in result['items']] == list(range(min(count,limit)))
    assert all(a is b for a,b in zip(selected,layer.selection))

@pytest.mark.parametrize('limit', [True,False,0,-1,257,64.0,'64',None,[],{}])
def test_invalid_limits_rejected(limit):
    _, _, read = setup()
    with pytest.raises(BridgeError) as error:
        read(['nodes'], {'kind':'selection','nodeLimit':limit})
    assert error.value.code == 'invalid_request'

@pytest.mark.parametrize('fields,selector,entities,code', [
    (['glyph'], {'kind':'selection','nodeLimit':64}, None, 'invalid_request'),
    (['nodes'], {'kind':'selection','glyph':'override'}, None, 'invalid_request'),
    (['nodes'], {'kind':'selection','offset':1}, None, 'invalid_request'),
    (['bogus'], None, None, 'unsupported_read'),
    (['nodes'], None, [{'kind':'selection'},{'kind':'selection'}], 'invalid_request'),
    (['nodes'], None, [{'kind':'selection'},{'kind':'glyph','id':'A'}], 'invalid_request'),
])
def test_invalid_scope_and_fields(fields, selector, entities, code):
    _, _, read = setup()
    with pytest.raises(BridgeError) as error: read(fields,selector,entities)
    assert error.value.code == code

@pytest.mark.parametrize('failure', ['missing-selection','parent','index','nan','smooth','type'])
def test_unavailable_evidence_is_an_error(failure):
    layer, _, read = setup()
    if failure == 'missing-selection': del layer.selection
    elif failure == 'parent': layer.selection[0].parent = NS()
    elif failure == 'index': layer.selection[0].index = 1
    elif failure == 'nan': layer.selection[0].position.x = float('nan')
    elif failure == 'smooth': layer.selection[0].smooth = None
    else: layer.selection[0].type = None
    with pytest.raises(BridgeError) as error: read(['nodes'])
    assert error.value.code == 'unsupported_read'
    assert 'native selection evidence unavailable' in error.value.message

def test_metadata_and_summary_do_not_access_paths_and_details_only_touch_returned_nodes():
    layer, _, read = setup(65)
    class BadPaths:
        def __iter__(self): raise AssertionError('unselected paths traversed')
    paths = layer.paths
    layer.paths = BadPaths()
    assert read(['glyph','layer','selectedNodeCount'])['selectedNodeCount'] == 65
    del layer.selection
    assert read(['glyph']) == {'glyph':'mixed'}
    layer.paths = paths
    layer.selection = list(paths[0].nodes)
    # Reading properties of an omitted node must not be necessary for truncation.
    layer.selection[64].parent = None
    assert read(['nodes'])['nodes']['complete'] is False
    with pytest.raises(BridgeError): read(['nodes'],{'kind':'selection','nodeLimit':65})

def test_selection_iterated_once_and_old_fields_unchanged():
    layer, _, read = setup()
    class Once:
        def __init__(self, nodes): self.nodes, self.calls = nodes, 0
        def __iter__(self):
            self.calls += 1
            assert self.calls == 1
            return iter(self.nodes)
    layer.selection = Once(layer.selection)
    assert read(SUMMARY+['nodes'])['nodes']['total'] == 3
    assert layer.selection.calls == 1
    layer.selection = []
    assert read(['glyph','layer','selectedNodeCount']) == dict(glyph='mixed',layer='opaque-layer',selectedNodeCount=0)

def test_selection_reference_uses_current_build_without_fallback():
    ref = (ROOT/'skills/glyphs/references/selection-reads.md').read_text()
    for phrase in ('selection.context.v1','selectedOtherCount','GSNode','Off-curves',
                   'no active Edit View','installation needs updating','sidecar and skills together',
                   'complete:false','layer.paths','path.nodes','1 to 256','need no job'):
        assert phrase in ref
    assert 'Older bridges without' not in ref
    assert 'Detailed positions' not in ref
