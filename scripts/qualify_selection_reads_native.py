"""Disposable native selection projection gate; no installed bridge or UI changes.

Run with glyphs run --app '/Applications/Glyphs 4.app' --plugins '' SCRIPT.
R06_SELECTION_OUT optionally chooses a new evidence directory.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import time
import traceback
from types import SimpleNamespace as NS

import objc
from GlyphsApp import Glyphs, GSFont, GSNode, GSAnchor, GSComponent, GSGuide, GSAnnotation, GSHint

DESKTOP = Path(__file__).resolve().parents[1]
ROOT = DESKTOP.parents[2]
OUT = Path(os.environ.get('R06_SELECTION_OUT', str(ROOT/'reports/v1-v2/06-selection-inspection/selection-context-implementation')))
OUT.mkdir(parents=True, exist_ok=True)
BASE = ROOT/'reports/v1-v2/06-selection-inspection/SelectionInspectionTest.glyphs'
for part in ('protocol', 'bridge'):
    sys.path.insert(0, str(DESKTOP/'src'/part))
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeError
import glyphs_mcp_bridge.glyphs_adapter as module
assert Path(module.__file__).is_relative_to(DESKTOP/'src/bridge')
ns = {'__file__':str(ROOT/'scripts/selection_fixture.py'), '__name__':'oracle'}
exec(compile(Path(ns['__file__']).read_text(), ns['__file__'], 'exec'), ns)
FIELDS = ['glyph','layer',*GlyphsAdapter.SELECTION_COUNTS,'nodes']
checks, samples = [], {}

def check(name, expected, observed):
    ok = expected == observed
    checks.append(dict(name=name, expected=expected, observed=observed, passed=ok))
    assert ok, name

def identity(obj):
    return int(objc.pyobjc_id(obj))

def proof(layer):
    return dict(width=layer.width, shapes=[identity(s) for s in layer.shapes],
        nodes=[(identity(n),identity(n.parent),n.position.x,n.position.y,str(n.type),bool(n.smooth),n.name,dict(n.userData or {})) for p in layer.paths for n in p.nodes],
        anchors=[identity(a) for a in layer.anchors], guides=[identity(g) for g in layer.guides],
        annotations=[(identity(a),a.position.x,a.position.y,a.text) for a in layer.annotations],
        hints=[(identity(h),identity(h.originNode),identity(h.targetNode)) for h in layer.hints],
        selection=[identity(s) for s in layer.selection])

def expected(layer, limit=64):
    # Independent enumeration of native paths/nodes, not the adapter's node.index.
    by_id = {identity(n):dict(x=n.position.x,y=n.position.y,type=str(n.type),smooth=bool(n.smooth),pathIndex=pi,nodeIndex=ni)
             for pi,p in enumerate(layer.paths) for ni,n in enumerate(p.nodes)}
    selected = list(layer.selection)
    counts = dict.fromkeys(GlyphsAdapter.SELECTION_COUNTS,0)
    entries = []
    for item in selected:
        if isinstance(item,GSNode): key='selectedNodeCount';entries.append(by_id[identity(item)])
        elif isinstance(item,GSAnchor): key='selectedAnchorCount'
        elif isinstance(item,GSComponent): key='selectedComponentCount'
        elif isinstance(item,GSGuide): key='selectedGuideCount'
        else:key='selectedOtherCount'
        counts[key]+=1
    return dict(glyph=layer.parent.name,layer=layer.layerId,**counts,
        nodes=dict(total=len(entries),returned=min(len(entries),limit),limit=limit,
                   complete=len(entries)<=limit,items=entries[:limit]))

def run(layer, title, limit=64):
    before=proof(layer)
    observed=GlyphsAdapter._selection_values(layer,{'kind':'selection','nodeLimit':limit},FIELDS)
    check(title+' values',expected(layer,limit),observed)
    check(title+' native preservation',before,proof(layer))
    return observed

baseline_hash=hashlib.sha256(BASE.read_bytes()).hexdigest()
try:
    with tempfile.TemporaryDirectory(prefix='glyphs-selection-context-') as temp:
        source=Path(temp)/BASE.name;shutil.copy2(BASE,source)
        font=GSFont(str(source))
        pristine=ns['snapshot'](font)
        for master in font.masters:
            layer=font.glyphs['mixed'].layers[master.id]
            # Variant only: components before paths, true smoothness, metadata,
            # a selectable native annotation, and a hint retaining node references.
            layer.shapes=list(layer.components)+list(layer.paths)
            layer.paths[0].nodes[4].smooth=True
            layer.paths[0].nodes[0].userData['selection-proof']='retain exactly'
            annotation=GSAnnotation();annotation.position=(33.125,44.375);annotation.text='Selection proof'
            layer.annotations.append(annotation)
            hint=GSHint();hint.originNode=layer.paths[0].nodes[0];hint.targetNode=layer.paths[0].nodes[4]
            layer.hints.append(hint)
            before_font=ns['snapshot'](font)
            nodes=[layer.paths[0].nodes[i] for i in (0,2,4)]
            objects=[layer.anchors['top'],layer.components[0],layer.guides[0],annotation]
            for name,selected in [('nodes',nodes),('empty',[]),('anchor',objects[:1]),
                                  ('component',objects[1:2]),('guide',objects[2:3]),
                                  ('other',objects[3:]),('mixed',nodes+objects)]:
                layer.selection=selected
                check(master.name+' '+name+' setup count',len(selected),len(layer.selection))
                run(layer,master.name+' '+name)
            check(master.name+' font data preserved',before_font,ns['snapshot'](font))
        layer=font.glyphs['many'].layers[font.masters[-1].id]
        # 260 nodes allows the >256 boundary without changing the baseline file.
        layer.shapes.append(layer.paths[0].copy())
        all_nodes=[n for p in layer.paths for n in p.nodes]
        for count in (0,3,63,64,65,255,256,257):
            layer.selection=all_nodes[:count]
            for limit in (1,32,64,256):run(layer,'boundary %s/%s'%(count,limit),limit)
        for count,limit in ((3,64),(256,64),(256,256)):
            layer.selection=all_nodes[:count]
            timings=[]
            for i in range(31):
                start=time.perf_counter()
                GlyphsAdapter._selection_values(layer,{'kind':'selection','nodeLimit':limit},FIELDS)
                elapsed=(time.perf_counter()-start)*1000
                if i:timings.append(elapsed)
            timings.sort()
            samples[str((count,limit))]=dict(n=len(timings),medianMs=statistics.median(timings),p95Ms=timings[28],maxMs=max(timings),samplesMs=timings,
                scope='isolated native projection wall time, not HTTP or installed bridge callback')
        adapter=GlyphsAdapter(NS(fonts=[font]));doc=adapter._id(font)
        check('no Edit View public adapter',dict(glyph=None,layer=None,nodes=None,**dict.fromkeys(GlyphsAdapter.SELECTION_COUNTS,0)),
            adapter.read_entities(doc,[{'kind':'selection'}],FIELDS)[0]['values'])
        check('baseline copy bytes unchanged',baseline_hash,hashlib.sha256(source.read_bytes()).hexdigest())
    check('baseline bytes unchanged',baseline_hash,hashlib.sha256(BASE.read_bytes()).hexdigest())
    result=dict(passed=True,checks=checks,samples=samples,module=module.__file__,host=dict(version=str(Glyphs.versionNumber),build=str(Glyphs.buildNumber)),scope='isolated native objects; Edit View activation and dirty UI flags require separate installed tests')
except Exception:
    result=dict(passed=False,checks=checks,samples=samples,error=traceback.format_exc())
(OUT/'native-source.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='checks'}))
assert result['passed'],result.get('error')
