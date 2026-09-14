"""Native contour correspondence, metadata/hints and bridge discard gate."""

import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
for part in ('sidecar','protocol','bridge'):sys.path.insert(0,str(ROOT/'src'/part))
import objc
from Foundation import NSPoint
from GlyphsApp import GSGlyph,GSFontMaster,GSLayer,GSPath,GSNode,GSHint,LINE,CURVE,OFFCURVE,STEM
from glyphs_mcp_sidecar import native_worker,start_node_job
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeCore


def drawn_segments(path):
    """Canonical directed native Bezier segments, independent of the start."""
    bezier=path.bezierPath;segments=[];current=start=None
    for index in range(bezier.elementCount()):
        kind,points=bezier.elementAtIndex_associatedPoints_(index)
        point=lambda p:(float(p[0]),float(p[1]))
        if kind==0:current=start=point(points[0])
        elif kind==1:
            end=point(points[0]);segments.append(('line',current,end));current=end
        elif kind==2:
            a,b,end=map(point,points[:3]);segments.append(('curve',current,a,b,end));current=end
        elif kind==3:
            if current!=start:segments.append(('line',current,start))
            current=start
        else:raise AssertionError('Unexpected native Bezier element')
    return min(tuple(segments[i:]+segments[:i]) for i in range(len(segments)))


def snapshot(layer):
    rings=[];metadata=[]
    for path in layer.paths:
        nodes=list(path.nodes)
        ring=[(float(n.position.x),float(n.position.y),str(n.type),bool(n.smooth)) for n in nodes]
        rings.append(min(tuple(ring[i:]+ring[:i]) for i in range(len(ring))))
        metadata+=sorted((int(objc.pyobjc_id(n)),int(n.userData['logicalNode'])) for n in nodes)
    hints=[(int(objc.pyobjc_id(h.originNode)),int(objc.pyobjc_id(h.targetNode))) for h in layer.hints]
    return rings,metadata,hints,float(layer.width),[drawn_segments(path) for path in layer.paths]


def main():
    font=native_worker._load_font(ROOT/'src/glyphs-mcp/tests/fixtures/headless-preview-minimal.glyphs')
    for glyph in list(font.glyphs):del font.glyphs[glyph.name]
    while len(font.masters)<3:font.masters.append(GSFontMaster())
    mids=[str(m.id) for m in font.masters]
    square=[(0,0,LINE),(100,0,LINE),(100,100,LINE),(0,100,LINE)]
    cubic=[(0,0,LINE),(30,0,OFFCURVE),(70,0,OFFCURVE),(100,100,CURVE),(0,100,LINE)]
    for name,points,rotations in [('landmark',square,[0,2,1]),('curved',cubic,[0,1,4])]:
        glyph=GSGlyph(name);font.glyphs.append(glyph)
        for mid,(sx,sy,tx,ty),rotation in zip(mids,[(1,1,0,0),(2,2,20.125,30.25),(.5,1.5,0,0)],rotations):
            layer=GSLayer();layer.layerId=mid;layer.associatedMasterId=mid;glyph.layers[mid]=layer
            path=GSPath();path.closed=True
            nodes=[]
            for i,(x,y,t) in enumerate(points):
                node=GSNode(NSPoint(x*sx+tx,y*sy+ty),t);node.userData['logicalNode']=i;nodes.append(node)
            for node in nodes[rotation:]+nodes[:rotation]:path.nodes.append(node)
            layer.shapes.append(path);layer.width=600.125
            oncurves=[n for n in path.nodes if n.type!=OFFCURVE]
            hint=GSHint();hint.type=STEM;hint.originNode=oncurves[0];hint.targetNode=oncurves[1];layer.hints.append(hint)
    root=Path(tempfile.mkdtemp(prefix='glyphs-start-node-native-'))
    wrapper=SimpleNamespace(glyphs=font.glyphs,masters=font.masters,filepath=str(root/'Fixture.glyphs'),
        parent=SimpleNamespace(isDocumentEdited=lambda:False,changeCount=lambda:0,undoManager=lambda:None))
    adapter=GlyphsAdapter(SimpleNamespace(fonts=[wrapper]));doc=adapter.list_documents()[0]
    request={'glyphs':['landmark','curved'],'options':{'referenceMaster':mids[0],'referenceNode':0}}
    changes,report=start_node_job.prepare(font,request)
    assert len(changes)==4,report
    baseline={(g.name,str(l.layerId)):snapshot(l) for g in font.glyphs for l in g.layers}
    original_hashes={(g.name,str(l.layerId)):adapter._outline_hash(l) for g in font.glyphs for l in g.layers}
    patch=dict(version=1,jobId='native-start-node',documentId=doc['id'],sourcePath=wrapper.filepath,
        sourceHash='sha256:'+'a'*64,generation=0,changes=changes,summary='Native contour correspondence gate')
    queue=[];core=BridgeCore(adapter,queue.append);core.begin_apply(patch)
    while queue:queue.pop(0)()
    assert core.operation(patch['jobId'])['status']=='applied',core.operation(patch['jobId'])
    assert all(snapshot(l)==baseline[(g.name,str(l.layerId))] for g in font.glyphs for l in g.layers)
    assert all(int(g.layers[mid].paths[0].nodes[0].userData['logicalNode'])==0 for g in font.glyphs for mid in mids)
    assert not start_node_job.prepare(font,request)[0]
    core.discard(patch['jobId'])
    while queue:queue.pop(0)()
    assert core.operation(patch['jobId'])['status']=='discarded',core.operation(patch['jobId'])
    assert all(adapter._outline_hash(l)==original_hashes[(g.name,str(l.layerId))] and snapshot(l)==baseline[(g.name,str(l.layerId))] for g in font.glyphs for l in g.layers)
    result=dict(threeMasterLandmarks=[r['landmarkNode'] for r in report['layers'] if r['glyph']=='landmark'],
        changes=len(changes),geometryIdentical=True,nodeObjectsAndMetadataPreserved=True,hintsPreserved=True,
        secondApplicationNoop=True,exactDiscard=True,scope='isolated native process; native Undo/Redo tested separately in editor')
    (ROOT/'build/start-node-native-benefit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
