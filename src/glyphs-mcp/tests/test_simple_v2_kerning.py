"""Collision benefit, native-resolution delegation and explicit kerning patches."""

from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
for part in ('sidecar', 'bridge', 'protocol'):
    sys.path.insert(0, str(ROOT / 'src' / part))
from glyphs_mcp_sidecar import collision, kerning_job, native_worker
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore
from glyphs_mcp_protocol import validate_patch, ProtocolError
from test_simple_v2_spacing import Collection, Layer


class Font:
    def __init__(self, before=None, group=-88):
        self.store = {('M1', 0, '@MMK_L_A', '@MMK_R_V'): group,
                      ('M1', 2, 'A', 'V'): -300.25, ('M2', 0, 'A', 'V'): -41.125}
        if before is not None: self.store[('M1', 0, 'A', 'V')] = before
        self.glyphs = Collection()
        self.masters = Collection(M1=NS(id='M1'))
        self.filepath = '/tmp/Kerning.glyphs'
        self.parent = NS(isDocumentEdited=lambda:False, changeCount=lambda:0, undoManager=lambda:None)
        for name, edge in [('A', lambda y:(100,500)), ('V', lambda y:(-20 if y == 50 else 0,200))]:
            layer = Layer(width=600, height=100, edge=edge)
            layer.nextKerningForLayer_direction_ = lambda right, direction:self.effective()
            self.glyphs[name] = NS(name=name, layers=Collection(M1=layer), rightKerningKey='@MMK_L_A',leftKerningKey='@MMK_R_V')
    def effective(self):
        # Deliberately keep precedence in this native stand-in, never in the job.
        return self.store.get(('M1',0,'A','V'), self.store[('M1',0,'@MMK_L_A','@MMK_R_V')])
    def kerningForPair(self, mid, left, right, direction=0): return self.store.get((mid,direction,left,right))
    def setKerningForPair(self, mid, left, right, number, direction=0): self.store[mid,direction,left,right]=number
    def removeKerningForPair(self, mid, left, right, direction=0): self.store.pop((mid,direction,left,right),None)


def test_refinement_reproduces_hidden_collision_and_retains_fractional_correction():
    font = Font()
    left, right = (font.glyphs[n].layers['M1'] for n in ('A','V'))
    result = collision.measure(left,right,-88,target_gap=5.125,dense_step=10)
    assert result['coarseGap'] == 12 and result['minGap'] == -8 and result['refined']
    changes, report = kerning_job.prepare(font,{'options':{'pairs':[['A','V']],'targetGap':5.125}})
    assert len(changes) == 1 and changes[0]['after'] == -74.875
    # Independent fixture geometry at its protrusion, not the measurement helper.
    assert 600 + changes[0]['after'] - 20 - 500 == 5.125
    assert report['pairs'][0]['storedBefore'] is None
    assert font.kerningForPair('M1','A','V') is None


@pytest.mark.parametrize('before', [None, 0.0, -90.125])
def test_external_patch_bridge_apply_and_discard_preserve_missing_zero_groups_and_other_domains(tmp_path, monkeypatch, before):
    font = Font(before)
    # A larger clearance objective exercises zero-valued existing exceptions too.
    adapter = GlyphsAdapter(NS(fonts=[font])); document = adapter.list_documents()[0]
    monkeypatch.setattr(native_worker,'_load_font',lambda path:font)
    patch = native_worker.build_patch({'source':font.filepath,'output':str(tmp_path/'patch.json'),
        'request':{'kind':'kerning_collision','options':{'pairs':[['A','V']],'targetGap':90.125}},
        'document':document,'jobId':'kerning-test','sourceHash':'sha256:'+'a'*64})
    saved = dict(font.store); change=patch['changes'][0]
    assert change['before'] == before and change['direction'] == 'LTR'
    queue=[];core=BridgeCore(adapter,queue.append);core.begin_apply(patch)
    while queue: queue.pop(0)()
    assert core.operation(patch['jobId'])['status']=='applied'
    assert font.effective() == change['after']
    assert all(font.store[k]==v for k,v in saved.items() if k != ('M1',0,'A','V'))
    result=core.read_entities(document['id'],[dict(kind='kerning',master='M1',direction='LTR',left='A',right='V')],['value'])
    assert result[0]['values']['value'] == change['after']
    core.discard(patch['jobId'])
    while queue: queue.pop(0)()
    assert core.operation(patch['jobId'])['status']=='discarded'
    assert font.store == saved


def test_sufficient_clearance_is_a_noop_and_uses_native_exception_over_group():
    font=Font(before=0)
    changes, report=kerning_job.prepare(font,{'options':{'pairs':[['A','V']]}})
    assert changes == [] and report['pairs'][0]['status']=='unchanged'
    assert report['pairs'][0]['effectiveBefore'] == 0
    assert not report['pairs'][0]['measurement']['refined']


def test_new_exception_does_not_modify_the_group():
    font=Font()
    changes,_=kerning_job.prepare(font,{'options':{'pairs':[['A','V']]}})
    assert changes[0]['left']=='A' and changes[0]['right']=='V'
    assert font.store['M1',0,'@MMK_L_A','@MMK_R_V'] == -88


@pytest.mark.parametrize('options', [{}, {'pairs':[['A']]}, {'pairs':[['A','V'],['A','V']]},
    {'pairs':[['A','V']],'denseStep':0}, {'pairs':[['A','V']],'targetGap':float('nan')},
    {'pairs':[['A','V']],'direction':'RTL'}])
def test_invalid_or_unsupported_collision_options_fail_explicitly(options):
    with pytest.raises(ValueError): collision.validate_options(options)


def test_kerning_contract_preserves_missing_zero_and_rejects_duplicate_pair():
    from test_simple_v2_protocol import patch
    value=patch()
    change=dict(kind='kerning',master='M1',direction='LTR',left='A',right='V',before=None,after=0.0)
    value['changes']=[change]
    assert validate_patch(value)['changes']==[change]
    for edit in ({'direction':'guess'},{'before':True},{'after':float('inf')}):
        value['changes']=[dict(change,**edit)]
        with pytest.raises(ProtocolError): validate_patch(value)
    value['changes']=[change,change]
    with pytest.raises(ProtocolError,match='duplicate'): validate_patch(value)


def test_stale_fractional_kerning_is_not_rebased_like_display_widths(tmp_path,monkeypatch):
    font=Font(before=-90.125)
    adapter=GlyphsAdapter(NS(fonts=[font]));doc=adapter.list_documents()[0]
    monkeypatch.setattr(native_worker,'_load_font',lambda path:font)
    patch=native_worker.build_patch({'source':font.filepath,'output':str(tmp_path/'patch.json'),
        'request':{'kind':'kerning_collision','options':{'pairs':[['A','V']]}},
        'document':doc,'jobId':'stale-pair','sourceHash':'sha256:'+'a'*64})
    font.setKerningForPair('M1','A','V',-90.12)
    queue=[];core=BridgeCore(adapter,queue.append);core.begin_apply(patch)
    while queue: queue.pop(0)()
    assert core.operation(patch['jobId'])['error']['code']=='target_conflict'
    assert font.effective()==-90.12


@pytest.mark.parametrize('direction,native', [('LTR',0),('RTL',2),('vertical',4)])
def test_stored_read_delegates_exact_keys_direction_and_preserves_order(direction,native):
    # Dispatch double only: installed native qualification establishes group semantics.
    font=Font();calls=[]
    values=iter([-90.125,0,None,-70.25])
    def read(mid,left,right,direction=0):
        calls.append((mid,left,right,direction));return next(values)
    font.kerningForPair=read
    adapter=GlyphsAdapter(NS(fonts=[font]));doc=adapter.list_documents()[0]
    pairs=[('A','V'),('o','V'),('X','Y'),('@MMK_L_A','@MMK_R_V')]
    targets=[dict(kind='kerning',master='M1',direction=direction,left=l,right=r) for l,r in pairs]
    result=BridgeCore(adapter,lambda callback:None).read_entities(doc['id'],targets,['value'])
    assert [x['values']['value'] for x in result]==[-90.125,0,None,-70.25]
    assert calls==[('M1',l,r,native) for l,r in pairs]
