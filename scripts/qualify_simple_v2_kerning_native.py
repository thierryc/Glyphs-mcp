"""Native collision benefit and kerning bridge gate, with plugins disabled."""

import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for part in ('sidecar','protocol','bridge'): sys.path.insert(0,str(ROOT/'src'/part))
from Foundation import NSPoint
from GlyphsApp import GSGlyph, GSLayer, GSPath, GSNode, GSComponent, LINE
from glyphs_mcp_sidecar import collision, kerning_job, native_worker
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore


def main():
    font=native_worker._load_font(ROOT/'src/glyphs-mcp/tests/fixtures/headless-preview-minimal.glyphs')
    for glyph in list(font.glyphs): del font.glyphs[glyph.name]
    mid=str(font.masters[0].id)
    root=Path(tempfile.mkdtemp(prefix='glyphs-kerning-native-'))
    for name,points in [('A',[(100,0),(500,0),(500,100),(100,100)]),
                        ('V',[(0,0),(200,0),(200,100),(0,100),(0,60),(-20,50),(0,40)]),
                        ('W',[(0,0),(200,0),(200,100),(0,100)])]:
        glyph=GSGlyph(name);font.glyphs.append(glyph)
        layer=GSLayer();layer.layerId=mid;layer.associatedMasterId=mid;glyph.layers[mid]=layer
        path=GSPath();path.closed=True
        for xy in points:path.nodes.append(GSNode(NSPoint(*xy),LINE))
        layer.shapes.append(path);layer.width=600
    a,v,w=(font.glyphs[n] for n in ('A','V','W'))
    a.rightKerningGroup='A';v.leftKerningGroup='V';w.leftKerningGroup='V'
    font.setKerningForPair(mid,'@MMK_L_A','@MMK_R_V',-88)
    ll,rl=a.layers[mid],v.layers[mid]
    assert ll.nextKerningForLayer_direction_(rl,0)==-88
    evidence=collision.measure(ll,rl,-88,target_gap=5.125,dense_step=10)
    assert evidence['coarseGap']==12 and evidence['minGap']==-8,evidence
    component_glyph=GSGlyph('V.component');font.glyphs.append(component_glyph)
    component_layer=GSLayer();component_layer.layerId=mid;component_layer.associatedMasterId=mid
    component_glyph.layers[mid]=component_layer;component_layer.shapes.append(GSComponent('V'));component_layer.width=600
    component_glyph.leftKerningGroup='V'
    component_changes,component_report=kerning_job.prepare(font,{'options':{'pairs':[['A','V.component']],'targetGap':5.125}})
    assert len(component_changes)==1,component_report
    assert component_report['pairs'][0]['measurement']['minGap']==-8
    wrapper=SimpleNamespace(glyphs=font.glyphs,masters=font.masters,filepath=str(root/'Fixture.glyphs'),
        parent=SimpleNamespace(isDocumentEdited=lambda:False,changeCount=lambda:0,undoManager=lambda:None),
        kerningForPair=font.kerningForPair,setKerningForPair=font.setKerningForPair,removeKerningForPair=font.removeKerningForPair)
    adapter=GlyphsAdapter(SimpleNamespace(fonts=[wrapper]));document=adapter.list_documents()[0]
    cases=[]
    for index,before in enumerate((None,0.0,-90.125)):
        if before is not None: font.setKerningForPair(mid,'A','V',before)
        else:font.removeKerningForPair(mid,'A','V')
        changes,report=kerning_job.prepare(font,{'options':{'pairs':[['A','V']],'targetGap':90.125}})
        assert len(changes)==1 and report['pairs'][0]['status']=='suggested',report
        patch=dict(version=1,jobId='kerning-native-'+str(index),documentId=document['id'],sourcePath=wrapper.filepath,
                   sourceHash='sha256:'+'a'*64,generation=0,changes=changes,summary='Native collision gate')
        queue=[];core=BridgeCore(adapter,queue.append);core.begin_apply(patch)
        while queue:queue.pop(0)()
        assert core.operation(patch['jobId'])['status']=='applied',core.operation(patch['jobId'])
        resolved=float(ll.nextKerningForLayer_direction_(rl,0))
        # Independent polygon coordinates at the protrusion, not scan output.
        clearance=float(ll.width)+resolved+min(float(n.position.x) for n in rl.paths[0].nodes)-max(float(n.position.x) for n in ll.paths[0].nodes)
        assert abs(clearance-90.125)<1e-9,clearance
        assert ll.nextKerningForLayer_direction_(w.layers[mid],0)==-88
        core.discard(patch['jobId'])
        while queue:queue.pop(0)()
        assert core.operation(patch['jobId'])['status']=='discarded',core.operation(patch['jobId'])
        assert font.kerningForPair(mid,'A','V')==before
        assert font.kerningForPair(mid,'@MMK_L_A','@MMK_R_V')==-88
        cases.append({'before':before,'after':changes[0]['after'],'independentClearance':clearance,'exactRestoration':True})
    font.setKerningForPair(mid,'A','V',0)
    changes,report=kerning_job.prepare(font,{'options':{'pairs':[['A','V']]}})
    assert not changes and report['pairs'][0]['status']=='unchanged'
    result=dict(benefit=evidence,cases=cases,nativeEffectiveResolution=True,groupPeerUnchanged=True,componentResolution=True,
                clearPairUnchanged=True,scope='isolated native process; editor gate separate')
    (ROOT/'build/kerning-native-benefit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
