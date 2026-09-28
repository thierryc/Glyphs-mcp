"""M8 language proofing is bounded read-only evidence, never an edit policy."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from test_simple_v2_kerning_edits import font
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeError


def api(): return importlib.import_module('glyphs_mcp_bridge.kerning_proof')


class Indexed(dict):
    def __iter__(self): return iter(self.values())
    def __getitem__(self, key):
        return list(self.values())[key] if type(key) is int else self.get(key)


def fixture(monkeypatch, rows=None):
    module = api()
    rows = rows or [('AV',['en','fr']),('VA',['en']),('AA',['fr']),('AZ',['en'])]
    monkeypatch.setattr(module.dataset, 'candidates', lambda languages: [(pair, [l for l in tags if l in languages]) for pair,tags in rows if set(tags)&set(languages)])
    f=font(); f.glyphs=Indexed(f.glyphs)
    for g in f.glyphs: g.unicode=f'{ord(g.name):04X}'
    adapter=GlyphsAdapter(NS(fonts=[f])); doc=adapter.list_documents()[0]['id']
    request=dict(kind='kerning_proof', master='M1', direction='LTR', languages=['en'], limit=1)
    return f,adapter,doc,request


def page(adapter,doc,request):
    return adapter.read_entities(doc,[request],['pairs'])[0]['values']


def pages(adapter,doc,request):
    seen=[]
    for _ in range(20):
        result=page(adapter,doc,request); seen.append(result)
        assert result['scannedGlyphs'] <= 256 and result['scannedCandidates'] <= 256
        assert len(result['items']) <= request['limit'] and len(result['skippedExamples']) <= 10
        if result['complete']: return seen
        request={**request,'cursor':result['nextCursor']}
    raise AssertionError('proof pagination did not finish')


def test_language_pages_include_covered_pairs_and_zero_exceptions_without_mutation(monkeypatch):
    f,a,d,r=fixture(monkeypatch); f.store['M1',0,'A','V']=0
    before=deepcopy(f.store)
    values=pages(a,d,r); items=[item for p in values for item in p['items']]
    assert [i['characters'] for i in items]==['AV','VA']
    first=items[0]
    assert first['proof']=='AV' and first['languages']==['en']
    assert first['coverage']['glyphPair']==0 and first['coverage']['groupPair']==-88
    assert first['coverage']['effective']['status']=='native' and first['coverage']['effective']['value']==0
    assert sum(p['skippedMissing'] for p in values)==1
    assert f.store==before
    assert all('suggestedValue' not in item and 'needsCorrection' not in item for item in items)


def test_ambiguous_unicode_is_skipped_not_guessed(monkeypatch):
    f,a,d,r=fixture(monkeypatch)
    alt=deepcopy(f.glyphs['A']); alt.name='A.alt'; alt.id='alt-id'; f.glyphs['A.alt']=alt
    result=pages(a,d,r)
    assert not [item for p in result for item in p['items']]
    assert sum(p['skippedAmbiguous'] for p in result)==3


def test_large_effective_value_is_not_a_missing_sentinel(monkeypatch):
    f,a,d,r=fixture(monkeypatch)
    f.glyphs['A'].layers['M1'].nextKerningForLayer_direction_=lambda *args:10000000000000.5
    result=pages(a,d,r)
    first=next(item for p in result for item in p['items'])
    assert first['coverage']['effective']==dict(status='native',value=10000000000000.5)


def test_mapping_scan_and_candidate_scan_are_bounded_and_reusable(monkeypatch):
    f,a,d,r=fixture(monkeypatch, [('ZZ',['en'])]*300)
    for i in range(600): f.glyphs[f'noUnicode{i}']=NS(name=f'noUnicode{i}', id=f'id{i}', unicode=None)
    first=page(a,d,r)
    assert first['phase']=='mapping' and first['scannedGlyphs']==256 and not first['items']
    all_pages=pages(a,d,{**r,'cursor':first['nextCursor']})
    assert all_pages[-1]['complete'] and sum(p['scannedCandidates'] for p in all_pages)==300
    repeat=page(a,d,r)
    assert repeat['scannedGlyphs']==0 and repeat['scannedCandidates']==256
    # Reads neither need a saved path nor clean document.
    f.filepath=None; f.parent.isDocumentEdited=lambda:True
    assert page(a,d,r)['scannedGlyphs']==256


def test_cursor_binds_language_master_direction_and_live_document(monkeypatch):
    f,a,d,r=fixture(monkeypatch); first=page(a,d,r)
    cursor=first['nextCursor']; assert cursor
    for changes in (dict(languages=['fr']),dict(master='M2'),dict(direction='RTL')):
        with pytest.raises(BridgeError): page(a,d,dict(r,**changes,cursor=cursor))
    f.parent.changeCount=lambda:1
    with pytest.raises(BridgeError): page(a,d,dict(r,cursor=cursor))


@pytest.mark.parametrize('change',[{'languages':['xx']},{'languages':[]},{'languages':['en','en']},{'direction':'auto'},{'limit':101},{'limit':True},{'apply':True}])
def test_invalid_proof_requests_fail_clearly(monkeypatch,change):
    f,a,d,r=fixture(monkeypatch)
    with pytest.raises(BridgeError): page(a,d,dict(r,**change))


def test_dataset_has_pinned_provenance_and_reproducible_contents():
    dataset=importlib.import_module('glyphs_mcp_protocol.kerning_dataset')
    root=Path(dataset.__file__).parent/'data'/'kerning-pairs'
    meta=json.loads((root/'provenance.json').read_text())
    assert meta['revision']=='b7a0e29ed81a8edee7b4b6cb1935ebf7d29ca611'
    assert meta['license']=='MIT' and len(meta['inputs'])==24
    assert 'André Fuchs' in (root/'LICENSE.md').read_text()
    assert set(dataset.languages())=={'cs','da','de','en','es','et','fi','fr','hr','hu','it','lt','lv','nl','no','pl','pt','ro','se','sk','sl','sq','sv','tr'}
    all_pairs=dataset.candidates(['en','fr'])
    assert all_pairs==dataset.candidates(['fr','en'])
    assert len({row[0] for row in all_pairs})==len(all_pairs)
    assert all(len(pair)==2 and set(tags)<= {'en','fr'} and tags for pair,tags in all_pairs)
    import hashlib
    assert hashlib.sha256((root/'pairs.json').read_bytes()).hexdigest()==meta['normalizedSha256']
