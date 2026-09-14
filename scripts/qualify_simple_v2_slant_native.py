"""Native slant/Cursivy comparison, optional stem benefit and exact discard."""

import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS

ROOT=Path(__file__).resolve().parents[1]
for part in ('sidecar','protocol','bridge'):sys.path.insert(0,str(ROOT/'src'/part))
import objc
from Foundation import NSPoint
from GlyphsApp import GSGlyph,GSLayer,GSPath,GSNode,GSMetric,GSComponent,GSAnchor,GSHint,LINE,CURVE,OFFCURVE,STEM
from glyphs_mcp_sidecar import native_worker,slant_job
from glyphs_mcp_sidecar.worker import WorkerError
from glyphs_mcp_sidecar.spacing import exact_copy
from glyphs_mcp_bridge import coordinates
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore


def perpendicular(layer):
    a,q,_,b=[n.position for n in layer.paths[0].nodes]
    vx,vy=b.x-a.x,b.y-a.y
    return abs(vx*(q.y-a.y)-vy*(q.x-a.x))/math.hypot(vx,vy)


def snapshot(layer):
    return dict(nodes=[[list(n.position) for n in p.nodes] for p in layer.paths],
        anchors=[(str(a.name),list(a.position)) for a in layer.anchors],
        components=[(str(c.componentName),list(c.transform),bool(c.automaticAlignment)) for c in layer.components],
        width=float(layer.width),topology=coordinates.signature(layer),
        metadata=[(int(objc.pyobjc_id(n)),int(n.userData['logicalNode']),bool(n.smooth)) for p in layer.paths for n in p.nodes],
        hints=[(int(objc.pyobjc_id(h.originNode)),int(objc.pyobjc_id(h.targetNode))) for h in layer.hints])


def main():
    font=native_worker._load_font(ROOT/'src/glyphs-mcp/tests/fixtures/headless-preview-minimal.glyphs')
    for glyph in list(font.glyphs):del font.glyphs[glyph.name]
    master=font.masters[0];mid=str(master.id)
    for name,horizontal in [('vertical',False),('horizontal',True)]:
        stem=GSMetric();stem.name=name;stem.horizontal=horizontal; font.stems.append(stem)
        master.setStemValueValue_forId_(100,stem.id)
    def layer(name):
        glyph=GSGlyph(name);font.glyphs.append(glyph)
        result=GSLayer();result.layerId=mid;result.associatedMasterId=mid;glyph.layers[mid]=result
        result.setTemporarilyDisableRounding_(True);result.width=600.125
        return result
    stem=layer('stemTest');curve=layer('curvedTest')
    for target,points in [(stem,[(0,0,LINE),(100,0,LINE),(100,800,LINE),(0,800,LINE)]),
        (curve,[(0,0,CURVE),(30,0,OFFCURVE),(70,0,OFFCURVE),(100,100,CURVE),(0,100,LINE)])]:
        path=GSPath();path.closed=True
        for i,(x,y,t) in enumerate(points):
            node=GSNode(NSPoint(x+.125,y+.25),t);node.userData['logicalNode']=i;path.nodes.append(node)
        target.shapes.append(path)
        target.anchors.append(GSAnchor('top',NSPoint(50.125,800.25)))
        hint=GSHint();hint.type=STEM;hint.originNode=path.nodes[0];hint.targetNode=path.nodes[-1];target.hints.append(hint)
    manual=layer('manualTest');automatic=layer('autoTest')
    for target,aligned in [(manual,False),(automatic,True)]:
        component=GSComponent('stemTest');target.shapes.append(component);component.automaticAlignment=aligned
        if not aligned:component.transform=(1,0,0,1,50.125,100.25)
        target.anchors.append(GSAnchor('top',NSPoint(100.125,800.25)))
    for target in (stem,curve,manual,automatic):target.setTemporarilyDisableRounding_(False)
    native=[]
    for mode in ('raw','cursivy','nativeThicknessOnly'):
        candidate=exact_copy(stem)
        if mode=='nativeThicknessOnly':candidate.slantX_origin_correctContrast_correctShape_correctThickness_checkSelection_(12,0,0,0,1,False)
        else:candidate.slantX_origin_doCorrection_checkSelection_(12,0,mode=='cursivy',False)
        measured=perpendicular(candidate)
        assert math.isclose(measured,100*math.cos(math.radians(12)),abs_tol=1e-9),(mode,measured)
        native.append(dict(mode=mode,perpendicularWidth=measured))
    root=Path(tempfile.mkdtemp(prefix='glyphs-slant-native-'))
    wrapper=NS(glyphs=font.glyphs,masters=font.masters,filepath=str(root/'Fixture.glyphs'),
        parent=NS(isDocumentEdited=lambda:False,changeCount=lambda:0,undoManager=lambda:None))
    adapter=GlyphsAdapter(NS(fonts=[wrapper]));doc=adapter.list_documents()[0]
    baseline={g.name:snapshot(g.layers[mid]) for g in font.glyphs}
    scenarios=[]
    for index,(names,correct) in enumerate([(['stemTest','curvedTest','manualTest','autoTest'],False),
        (['stemTest','curvedTest','manualTest','autoTest'],True),(['manualTest'],True)]):
        font.grid=0
        changes,report=slant_job.prepare(font,{'glyphs':names,'options':{'angle':12,'pivotY':300.125,'preserveStraightStems':correct}})
        # Real bridge setters must preserve the private candidate's fractions
        # with the editor's ordinary integral grid, without changing that grid.
        font.grid=1
        queue=[];core=BridgeCore(adapter,queue.append)
        patch=dict(version=1,jobId='native-slant-'+str(index),documentId=doc['id'],sourcePath=wrapper.filepath,
            sourceHash='sha256:'+'a'*64,generation=adapter.list_documents()[0]['generation'],changes=changes,summary='Slant fixture')
        core.begin_apply(patch)
        while queue:queue.pop(0)()
        operation=core.operation(patch['jobId'])
        assert operation['status']=='applied',operation.get('error')
        for change in changes:assert adapter.current_value(doc['id'],change)==change['after']
        for name in names:
            after=snapshot(font.glyphs[name].layers[mid])
            for field in ('width','topology','metadata','hints'):assert after[field]==baseline[name][field],(name,field)
        if 'stemTest' in names:
            expected=100 if correct else 100*math.cos(math.radians(12))
            assert math.isclose(perpendicular(stem),expected,abs_tol=1e-9),perpendicular(stem)
            # Curve-only correction has no accepted straight pair.
            row=next(r for r in report['layers'] if r['glyph']=='curvedTest')
            assert row['correction']['compensatedPairCount']==0
            t=math.tan(math.radians(12));x,y=baseline['stemTest']['anchors'][0][1]
            assert all(math.isclose(a,b,abs_tol=1e-9) for a,b in zip(stem.anchors['top'].position,[x+t*(y-300.125),y]))
        t=math.tan(math.radians(12));a,b,c,d,tx,ty=baseline['manualTest']['components'][0][1]
        expected_c=t*(d-a) if 'stemTest' in names else t*d
        expected_tx=tx+t*(ty-300.125)+(a*t*300.125 if 'stemTest' in names else 0)
        matrix=list(manual.components[0].transform)
        assert math.isclose(matrix[2],expected_c,abs_tol=1e-12) and math.isclose(matrix[4],expected_tx,abs_tol=1e-12),matrix
        assert snapshot(automatic)['components']==baseline['autoTest']['components']
        assert font.grid==1 and all(not l.temporarilyDisableRounding() for g in font.glyphs for l in g.layers)
        measured=perpendicular(stem)
        core.discard(patch['jobId'])
        while queue:queue.pop(0)()
        operation=core.operation(patch['jobId']);assert operation['status']=='discarded',operation.get('error')
        assert {g.name:snapshot(g.layers[mid]) for g in font.glyphs}==baseline
        scenarios.append(dict(selected=names,preserveStraightStems=correct,changes=len(changes),
            measuredStemWidth=measured,exactApply=True,exactDiscard=True))
    manual.components[0].transform=(1.125,0,0,.875,50.125,100.25)
    unsupported=snapshot(manual)
    try:slant_job.prepare(font,{'glyphs':['stemTest','manualTest']})
    except WorkerError as error:assert 'cannot round-trip exactly' in str(error)
    else:raise AssertionError('lossy native matrix must be rejected before live writes')
    assert snapshot(manual)==unsupported
    result=dict(passed=True,nativeComparison=native,scenarios=scenarios,topologyMetadataHintsPreserved=True,
        anchorsFollowNativeSlant=True,manualComponentsAvoidDoubleShear=True,automaticComponentLocalDataPreserved=True,
        editorGridPreserved=True,lossyNativeMatricesRejected=True,claim='Accepted straight-stem width preservation only; native comparison limited to this fixture.')
    (ROOT/'build/slant-native-benefit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
