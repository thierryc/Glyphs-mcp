"""M8: exact assignments are typed, bounded, read-only in preparation and reversible."""
from copy import deepcopy
import importlib
import math
from types import SimpleNamespace as NS

import pytest

from test_simple_v2_kerning import Font, Collection, GlyphsAdapter
from test_simple_v2_exact_history import History
from glyphs_mcp_protocol import ProtocolError
from glyphs_mcp_protocol.preparation import consume, simple
from glyphs_mcp_bridge.core import BridgeCore
from glyphs_mcp_sidecar.service import SidecarService, ServiceError


def api():
    return importlib.import_module('glyphs_mcp_protocol.kerning_edits')


def side(name):
    return {'kind': 'group', 'key': name} if name.startswith('@') else {'kind': 'glyph', 'name': name}


def edit(left='A', right='V', *, op='set', value=-72.5, direction='LTR', master='M1'):
    item = dict(op=op, master=master, direction=direction, left=side(left), right=side(right))
    if op == 'set': item['value'] = value
    return item


def request(*edits):
    return dict(kind='kerning_edit', glyphs=[], options=dict(edits=list(edits or [edit()])))


def font():
    value = Font()
    value.masters['M2'] = NS(id='M2')
    for name, glyph in value.glyphs.items():
        glyph.id = 'id_' + name
        glyph.rightKerningGroup = 'A' if name == 'A' else None
        glyph.leftKerningGroup = 'V' if name == 'V' else None
        glyph.topKerningGroup = 'top_' + name
        glyph.bottomKerningGroup = 'bottom_' + name
    return value


def prepared(value, *edits):
    r = request(*edits)
    return consume(simple.iterator(value, r))


def test_exact_request_is_native_and_rejects_legacy_top_level_selection():
    r = request()
    assert simple.eligible(r)
    assert simple.validate_request(r) == r
    assert SidecarService._job_request('kerning_edit', None, None, r['options']) == r
    for kwargs in [(1, None), (None, ['A'])]:
        with pytest.raises(ServiceError): SidecarService._job_request('kerning_edit', *kwargs, r['options'])


@pytest.mark.parametrize('direction,native', [('LTR', 0), ('RTL', 2), ('vertical', 4)])
@pytest.mark.parametrize('left,right', [('A','V'), ('A','@MMK_R_V'), ('@MMK_L_A','V'), ('@MMK_L_A','@MMK_R_V')])
def test_set_zero_delete_and_native_history_preserve_other_pairs(direction, native, left, right):
    # Direction-specific group keys are qualified separately against the native wrapper.
    if direction != 'LTR' and ('@' in left or '@' in right):
        left = {'RTL': '@MMK_R_V', 'vertical': '@MMK_T_bottom_A'}[direction] if left.startswith('@') else left
        right = {'RTL': '@MMK_L_A', 'vertical': '@MMK_B_top_V'}[direction] if right.startswith('@') else right
    f = font(); original = deepcopy(f.store)
    adapter = GlyphsAdapter(NS(fonts=[f])); doc = adapter.list_documents()[0]
    history = History(); history.isUndoRegistrationEnabled = lambda: True; f.parent.undoManager = lambda: history
    for g in f.glyphs:
        g.layers['M1'].undoManager = lambda: history
    key = ('M1', native, left, right)
    for wanted in [-72.5, 0, None]:
        history.actions.clear()
        before = deepcopy(f.store)
        changes, report = prepared(f, edit(left, right, direction=direction, op='remove' if wanted is None else 'set', value=wanted))
        assert f.store == before, 'preparation must never call a live setter'
        assert len(changes) == 1 and changes[0]['before'] == before.get(key) and changes[0]['after'] == wanted
        assert report['pairs'][0]['status'] == 'changed'
        adapter.begin_undo(doc['id']); adapter.apply_change(doc['id'], changes[0]); adapter.end_undo(doc['id'], 'Exact kerning')
        assert f.store.get(key) == wanted and (key in f.store) == (wanted is not None)
        assert {k:v for k,v in f.store.items() if k != key} == {k:v for k,v in before.items() if k != key}
        history.undo(); assert f.store == before
        history.undo(); assert f.store.get(key) == wanted and (key in f.store) == (wanted is not None)
    # Absence is a no-op; explicit zero is an actual stored exception.
    changes, report = prepared(f, edit(left, right, direction=direction, op='remove'))
    assert changes == [] and report['pairs'][0]['status'] == 'unchanged'


@pytest.mark.parametrize('bad', [
    {'op':'delete'}, {'direction':'auto'}, {'master':''}, {'value':True},
    {'value':float('nan')}, {'value':float('inf')}, {'value':None},
    {'left':{'kind':'glyph','name':'@MMK_L_A'}},
    {'left':{'kind':'group','key':'A'}}, {'right':{'kind':'glyph','name':''}},
    {'right':{'kind':'glyph','name':'V','extra':True}}, {'surprise':True},
])
def test_request_rejects_ambiguous_or_nonfinite_assignment(bad):
    row = dict(edit(), **bad)
    with pytest.raises(ProtocolError): api().validate_options({'edits':[row]})


def test_zero_is_not_remove_and_batch_boundary_is_exact():
    assert api().validate_options({'edits':[edit(value=0)]})['edits'][0]['value'] == 0
    with pytest.raises(ProtocolError): api().validate_options({'edits':[dict(edit(op='remove'), value=0)]})
    rows = [edit(left='g'+str(i)) for i in range(100)]
    assert len(api().validate_options({'edits':rows})['edits']) == 100
    for bad in [[], rows+[edit(left='overflow')], [edit(),edit()], [edit(),edit(op='remove')]]:
        with pytest.raises(ProtocolError): api().validate_options({'edits':bad})


@pytest.mark.parametrize('row', [edit(left='missing'),edit(master='missing'),edit(left='@MMK_L_missing')])
def test_invalid_target_after_valid_entry_is_atomic(row):
    f=font();before=deepcopy(f.store)
    with pytest.raises(ValueError): prepared(f, edit(), row)
    assert f.store == before


def test_unchanged_and_missing_removal_produce_no_patch():
    f=font(); f.store['M1',0,'A','V']=0
    changes,report=prepared(f,edit(value=0),edit('V','A',op='remove'))
    assert changes == [] and report['noChangeCount']==2


def test_prepared_identity_guard_rejects_replaced_glyph_or_changed_group():
    f=font();changes,_=prepared(f,edit())
    adapter=GlyphsAdapter(NS(fonts=[f]));doc=adapter.list_documents()[0]
    f.glyphs['A'].id='replacement'
    with pytest.raises(ValueError): adapter.current_value(doc['id'],changes[0])


@pytest.mark.parametrize('left,right', [('A','V'), ('A','@MMK_R_V'),
                                      ('@MMK_L_A','V'), ('@MMK_L_A','@MMK_R_V')])
def test_glyph_history_suppresses_native_document_registration(left, right):
    f = font(); changes, _ = prepared(f, edit(left, right))
    document_history, glyph_history = History(), History()
    for h in (document_history, glyph_history): h.isUndoRegistrationEnabled = lambda h=h: h.enabled
    f.parent.undoManager = lambda: document_history
    f.glyphs['A'].layers['M1'].undoManager = lambda: glyph_history
    setter = f.setKerningForPair
    def native_setter(*a, **k):
        assert not document_history.enabled, 'native font setter also registers document Undo'
        setter(*a, **k)
    f.setKerningForPair = native_setter
    adapter = GlyphsAdapter(NS(fonts=[f])); doc = adapter.list_documents()[0]
    adapter.begin_undo(doc['id']); adapter.apply_change(doc['id'], changes[0]); adapter.end_undo(doc['id'], 'Kerning')
    assert document_history.enabled and not document_history.actions
    assert len(glyph_history.actions) == 1
    glyph_history.undo(); glyph_history.undo()
    assert document_history.enabled and not document_history.actions
    f=font();changes,_=prepared(f,edit('@MMK_L_A','@MMK_R_V'))
    adapter=GlyphsAdapter(NS(fonts=[f]));doc=adapter.list_documents()[0]
    f.glyphs['A'].rightKerningGroup='another'
    with pytest.raises(ValueError): adapter.current_value(doc['id'],changes[0])


@pytest.mark.parametrize('direction,left', [('LTR','@MMK_L_A'), ('RTL','@MMK_R_V'),
                                           ('vertical','@MMK_T_bottom_A')])
@pytest.mark.parametrize('wanted', [-72.5, 0, None])
@pytest.mark.parametrize('selected', ['member', 'unrelated', 'other_master', 'none'])
def test_group_history_uses_matching_active_member_or_prepared_anchor(direction, left, wanted, selected):
    f = font()
    # Add a second member after the representative, with a distinct history.
    anchor = f.glyphs['V' if direction == 'RTL' else 'A']
    member = NS(**vars(anchor)); member.name = 'member'; member.id = 'id_member'
    member.layers = Collection(M1=NS(layerId='M1', parent=member))
    f.glyphs['member'] = member
    unrelated = f.glyphs['A' if direction == 'RTL' else 'V']
    unrelated.layers['M1'].layerId = 'M1'; unrelated.layers['M1'].parent = unrelated
    f.selectedLayers = {'member':[member.layers['M1']], 'unrelated':[unrelated.layers['M1']],
                        'other_master':[NS(layerId='M2', parent=member)], 'none':[]}[selected]
    document_history, anchor_history, member_history = History(), History(), History()
    for h in (document_history, anchor_history, member_history):
        h.isUndoRegistrationEnabled = lambda h=h: h.enabled
    f.parent.undoManager = lambda: document_history
    anchor.layers['M1'].undoManager = lambda: anchor_history
    member.layers['M1'].undoManager = lambda: member_history
    native = api().DIRECTIONS[direction]; key = ('M1',native,left,'V')
    f.store[key] = -40.125
    before = deepcopy(f.store)
    changes, _ = prepared(f, edit(left,'V',direction=direction,
                                 op='remove' if wanted is None else 'set', value=wanted))
    adapter = GlyphsAdapter(NS(fonts=[f])); doc = adapter.list_documents()[0]
    adapter.begin_undo(doc['id']); adapter.apply_change(doc['id'],changes[0]); adapter.end_undo(doc['id'],'Kerning')
    history = member_history if selected == 'member' else anchor_history
    other = anchor_history if selected == 'member' else member_history
    assert len(history.actions) == 1 and not other.actions and not document_history.actions
    assert history.level == 0 and history.automatic and history.enabled
    after = deepcopy(f.store)
    assert after.get(key) == wanted and (key in after) == (wanted is not None)
    history.undo(); assert f.store == before
    history.undo(); assert f.store == after
    assert not other.actions and not document_history.actions and document_history.enabled


def test_guarded_group_edit_refuses_missing_glyph_history_without_document_fallback():
    f = font(); changes, _ = prepared(f, edit('@MMK_L_A','V'))
    document_history = History(); document_history.isUndoRegistrationEnabled = lambda: True
    f.parent.undoManager = lambda: document_history
    before = deepcopy(f.store)
    adapter = GlyphsAdapter(NS(fonts=[f])); doc = adapter.list_documents()[0]
    adapter.begin_undo(doc['id'])
    try:
        with pytest.raises(ValueError,match='Native kerning Undo is unavailable'):
            adapter.apply_change(doc['id'],changes[0])
    finally:
        adapter.end_undo(doc['id'],'Refused')
    assert f.store == before and not document_history.actions and document_history.level == 0


def test_exact_native_table_read_does_not_turn_large_values_into_absence():
    f=font()
    class Table(dict):
        def objectForKey_(self,key): return self.get(key)
    f.kerningLTR=Table(M1=Table(id_A=Table(id_V=2000000.5)))
    f.kerningForPair=lambda *a,**k:None  # Glyphs wrapper's >1,000,000 sentinel heuristic.
    changes,_=prepared(f,edit(value=0))
    assert changes[0]['before']==2000000.5
    adapter=GlyphsAdapter(NS(fonts=[f]));doc=adapter.list_documents()[0]
    assert adapter.current_value(doc['id'],changes[0])==2000000.5


def test_conversation_scope_and_preview_show_pairs_and_explicit_removal():
    from glyphs_mcp_sidecar.edit_workflow_state import public_workflow
    import shutil, subprocess
    from pathlib import Path
    r=request(edit(value=0),edit('V','A',op='remove'))
    state=public_workflow(dict(id='edit_kerning',nonce='nonce',revision=1,state='ready',
        document=dict(id='doc_1',familyName='Fixture'),request=r,job=dict(changeCount=2)))
    assert state['scope']['targets']==r['options']['edits']
    assert '2 exact pair edits' in state['text']
    node=shutil.which('node')
    if not node:pytest.skip('Node needed for card rendering')
    root=Path(__file__).resolve().parents[3]
    subprocess.run([node,str(Path(__file__).parent/'fixtures/kerning_workflow_host.js'),
        str(root/'src/sidecar/glyphs_mcp_sidecar/edit_workflow_v1.html')],check=True,timeout=15)


def test_exact_route_requires_native_capability_and_never_worker_fallback(tmp_path):
    from glyphs_mcp_sidecar.jobs import JobStore
    status=dict(writeCapabilities=['kerning.edit.exact.v1'],jobCapabilities=[simple.CAPABILITY])
    worker=NS(status=lambda:(_ for _ in ()).throw(AssertionError('exact edits do not query worker availability')))
    service=SidecarService(NS(status=lambda:status),jobs=JobStore(tmp_path),worker=worker)
    try:
        assert service.validate_job_request('kerning_edit',options=request()['options'])==request()
        status['jobCapabilities']=[]
        with pytest.raises(ServiceError,match='native'):
            service.validate_job_request('kerning_edit',options=request()['options'])
        status['jobCapabilities']=[simple.CAPABILITY];status['writeCapabilities']=[]
        with pytest.raises(ServiceError,match='native'):
            service.validate_job_request('kerning_edit',options=request()['options'])
    finally:service.close()
