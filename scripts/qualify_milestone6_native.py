"""Three full-font native preparation/apply/recovery cycles on disposable files.

This is a detached regression. It does not replace the visible editor gate.
"""
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace as NS

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'/p) for p in ('protocol','sidecar','bridge')]
from glyphs_mcp_sidecar import native_worker,spacing_job
from glyphs_mcp_sidecar.source import source_hash
from glyphs_mcp_bridge.core import BridgeCore
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from GlyphsApp import GSPackageBundle
from Foundation import NSURL

def save(font,path):
    result=font.saveToURL_type_error_(NSURL.fileURLWithPath_(str(path)),GSPackageBundle,None)
    assert result[0],result

original=Path(sys.argv[1]).resolve()
original_hash=source_hash(original)
work=Path(tempfile.mkdtemp(prefix='glyphs-m6-native-')).resolve()
source=work/'Disposable.glyphspackage';control=work/'Control.glyphspackage'
shutil.copytree(original,source);shutil.copytree(original,control)
font=native_worker._load_font(source)
control_font=native_worker._load_font(control)
save(control_font,control)
wrapper=NS(glyphs=font.glyphs,masters=font.masters,familyName=font.familyName,filepath=str(source),
           parent=NS(isDocumentEdited=lambda:False,changeCount=lambda:0,undoManager=lambda:None))
adapter=GlyphsAdapter(NS(fonts=[wrapper]));document=adapter.list_documents()[0]

def values():
    return {(str(g.name),str(l.layerId)):(float(l.width),spacing_job.layer_hash(l))
            for g in font.glyphs for l in g.layers if l.isMasterLayer}

baseline=values();rows=[]
for cycle in range(1,4):
    output=work/f'cycle-{cycle}';output.mkdir()
    patch=native_worker.build_patch({'request':{'kind':'spacing','options':{}},'source':str(source),
        'sourceHash':source_hash(source),'jobId':f'm6-native-{cycle}','document':document,'output':str(output/'patch.json')})
    report=json.loads((output/'report.json').read_text())
    assert not [r for r in report['layers'] if r['status']=='unavailable'],report
    queue=[];bridge=BridgeCore(adapter,schedule=queue.append)
    bridge.begin_apply(patch)
    while queue: queue.pop(0)()
    assert bridge.operation(patch['jobId'])['status']=='applied',bridge.operation(patch['jobId'])
    expected=dict(baseline)
    for change in patch['changes']:
        key=(change['glyph'],change['layer']);width,outline=expected[key]
        expected[key]=(change['after'],outline) if change['kind']=='set' else (width,change['afterHash'])
    assert values()==expected
    bridge.discard(patch['jobId'])
    while queue: queue.pop(0)()
    assert bridge.operation(patch['jobId'])['status']=='discarded',bridge.operation(patch['jobId'])
    assert values()==baseline
    assert source_hash(original)==original_hash
    row={'cycle':cycle,'masterLayers':len(baseline),'writes':len(patch['changes']),'unavailable':0,'exactApply':True,'exactRecovery':True}
    rows.append(row);print(json.dumps(row),flush=True)
save(font,source)
files=lambda p:{f.relative_to(p).as_posix():f.read_bytes() for f in p.rglob('*') if f.is_file()}
a,b=files(source),files(control)
differences=sorted(k for k in a.keys()|b.keys() if a.get(k)!=b.get(k))
assert not differences,differences
assert source_hash(original)==original_hash
result={'cycles':rows,'savedMatchesNativeControl':True,'originalUnchanged':True,'originalHash':original_hash,
        'disposable':str(source),'control':str(control),'scope':'detached native process; visible editor acceptance is separate'}
(ROOT/'build/milestone6-native-heavy.json').write_text(json.dumps(result,indent=2)+'\n')
