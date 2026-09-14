"""Isolated native Report 05 regression gate; never operates on editor documents."""
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for part in ('protocol', 'bridge'):
    sys.path.insert(0, str(ROOT/'src'/part))
from GlyphsApp import Glyphs, GSFont
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
import glyphs_mcp_bridge.glyphs_adapter as adapter_module
assert Path(adapter_module.__file__).resolve().is_relative_to(ROOT/'src'), 'Candidate source required; run with --plugins empty'

BASE = Path(os.environ['R05_BASELINE'])
OUT = Path(os.environ['R05_NATIVE_OUT'])
spec = json.loads((BASE/'expected.json').read_text())
oracle = json.loads((BASE/'v2-native.json').read_text())
font = GSFont(spec['baseline'])
adapter = GlyphsAdapter(Glyphs)
adapter._fonts = lambda: [font]
core = BridgeCore(adapter, lambda callback: callback())
doc = core.list_documents()[0]['id']
checks = []
completed = False

def check(name, value):
    checks.append({'name':name,'passed':bool(value)})
    assert value, name

def read(selectors, fields=['id','name','width']):
    return core.read_entities(doc, selectors, fields)

def reject(selector, code):
    try: read([selector])
    except BridgeError as exc: check(str(selector)+' rejected', exc.code == code)
    else: check(str(selector)+' must reject', False)

try:
    expected = {(r['glyph'],r['id']):r['values'] for r in oracle['rows']}
    selectors = [{'kind':'layer','glyph':g,'id':m.id} for g in spec['core']+spec['batch'] for m in font.masters]
    values = []
    for i in range(0,len(selectors),100): values += read(selectors[i:i+100], ['id',*spec['fields']])
    check('123 native IDs returned exactly', [r['values']['id'] for r in values] == [r['id'] for r in selectors])
    check('123 native metric/bounds rows unchanged', all({k:v for k,v in r['values'].items() if k!='id'} == expected[(r['entity']['glyph'],r['entity']['id'])] for r in values))
    glyph = font.glyphs['control']
    original = glyph.layers[font.masters[0].id]
    backup = original.copy();backup.layerId='opaque-backup';backup.associatedMasterId=font.masters[0].id
    backup.name=font.masters[1].id;glyph.layers[backup.layerId] = backup
    special = original.copy();special.layerId='opaque-special';special.associatedMasterId=font.masters[0].id
    special.attributes['coordinates']={font.axes[0].axisId: 500};glyph.layers[special.layerId] = special
    duplicate = original.copy();duplicate.layerId='opaque-duplicate';duplicate.associatedMasterId=font.masters[0].id
    duplicate.name='Light';glyph.layers[duplicate.layerId] = duplicate
    check('native special layer recognized', special.isSpecialLayer)
    ids=[font.masters[1].id,'opaque-backup','opaque-special','opaque-duplicate']
    rows=read([{'kind':'layer','glyph':'control','id':key} for key in ids])
    check('exact native IDs resolve special/backup/name collision', [r['values']['id'] for r in rows]==ids)
    check('ID resolves ordinary layer before colliding backup name', rows[0]['values']['width']==600.625)
    for field in ['id','glyph']:
        for value in [None,'',0,True]:
            selector={'kind':'layer','glyph':'control','id':font.masters[0].id};selector[field]=value
            reject(selector,'invalid_request')
        selector={'kind':'layer','glyph':'control','id':font.masters[0].id};del selector[field]
        reject(selector,'invalid_request')
    for value in ['Light', str(special.name), 'missing']:
        reject({'kind':'layer','glyph':'control','id':value},'target_not_found')
    try: read([selectors[0],{'kind':'layer','glyph':'control','id':'missing'}])
    except BridgeError as exc: check('mixed request fails without partial results',exc.code=='target_not_found')
    else:check('mixed request rejected',False)
    check('reads do not replace native layer objects', glyph.layers[original.layerId] == original and glyph.layers[backup.layerId] == backup)
    check('baseline bytes unchanged',hashlib.sha256(Path(spec['baseline']).read_bytes()).hexdigest()==spec['sha256'])
    completed = True
finally:
    OUT.write_text(json.dumps({'host':{'version':str(Glyphs.versionNumber),'build':str(Glyphs.buildNumber)},'completed':completed,'checks':checks,'passed':completed and bool(checks) and all(c['passed'] for c in checks)},indent=2)+'\n')
print(json.dumps({'passed':True,'checks':len(checks)}))
