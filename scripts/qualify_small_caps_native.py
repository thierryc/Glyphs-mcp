"""Native mechanical qualification on a supplied disposable font only.

CLI: run with glyphs-cli (no live fonts are used). In a native script job load
this file with runpy.run_path and call qualify(font) on the exact test document.
Reports describe synthetic fixture checks, not optical approval of a typeface.
"""
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]


def qualify(font=None):
    from GlyphsApp import Glyphs, GSFont, GSFontMaster, GSGlyph, GSPath, GSNode, GSAnchor, GSComponent
    helper = runpy.run_path(str(ROOT/'skills/glyphs-mcp-small-caps/scripts/derive_caps.py'))
    run, precise = helper['run_caps'], helper['precision']
    if font is None:
        font = GSFont(); font.familyName = 'Small caps synthetic qualification'; font.masters = []
    if len(font.glyphs):
        raise ValueError('Qualification requires an empty disposable font')
    while len(font.masters) < 2:
        font.masters.append(GSFontMaster())
    masters = [str(m.id) for m in font.masters]
    for m in font.masters:
        m.capHeight = 700; m.xHeight = 500

    def polygon(layer, points):
        path = GSPath(); path.closed = True
        for xy in points:
            path.nodes.append(GSNode(xy, type='line'))
        layer.shapes.append(path)
        return path

    def ellipse(layer, left, bottom, right, top, reverse=False):
        cx,cy = (left+right)/2,(bottom+top)/2
        rx,ry = (right-left)/2,(top-bottom)/2
        k=.5522847498307936
        path=GSPath();path.closed=True
        entries=[((cx,top),'curve'),((cx+k*rx,top),'offcurve'),((right,cy+k*ry),'offcurve'),
            ((right,cy),'curve'),((right,cy-k*ry),'offcurve'),((cx+k*rx,bottom),'offcurve'),
            ((cx,bottom),'curve'),((cx-k*rx,bottom),'offcurve'),((left,cy-k*ry),'offcurve'),
            ((left,cy),'curve'),((left,cy+k*ry),'offcurve'),((cx-k*rx,top),'offcurve')]
        for xy,kind in entries:path.nodes.append(GSNode(xy,type=kind))
        if reverse:path.reverse()
        layer.shapes.append(path)

    for name in ('H','O','A','acutecomb.case','Aacute','Z'):
        font.glyphs.append(GSGlyph(name))
    for index,mid in enumerate(masters):
        stem=80+index*25
        for name in ('H','O','A','acutecomb.case','Z'):
            layer=font.glyphs[name].layers[mid]
            with precise(layer):
                layer.width=600.25
                if name=='H':
                    polygon(layer,[(50,0),(50+stem,0),(50+stem,310),(450-stem,310),
                        (450-stem,0),(450,0),(450,700),(450-stem,700),
                        (450-stem,390),(50+stem,390),(50+stem,700),(50,700)])
                    # Serif fixture, with designed overlaps retained in the second master.
                elif name=='O':
                    ellipse(layer,40,-12,460,712)
                    ellipse(layer,40+stem,50-index*10,460-stem,650+index*10,True)
                elif name=='A':
                    polygon(layer,[(30,0),(200,700),(300,700),(470,0),(380,0),(250,550),(120,0)])
                elif name=='acutecomb.case':
                    polygon(layer,[(0,0),(60,0),(120,130),(30,130)])
                else:
                    polygon(layer,[(40,0),(460,700),(40,700),(460,0)]).closed=False
                layer.anchors.append(GSAnchor('_top' if name=='acutecomb.case' else 'top',
                                             (30,0) if name=='acutecomb.case' else (250.25,730.5)))
        composite=font.glyphs['Aacute'].layers[mid]
        composite.shapes.append(GSComponent('A'));composite.shapes.append(GSComponent('acutecomb.case'))
        composite.doAlignComponents()
    inventory=runpy.run_path(str(ROOT/'src/bridge/glyphs_mcp_bridge/native_filters.py'))['inventory']()
    offset=None; qualification=None
    if inventory['available']:
        adapter=next((f for f in Glyphs.filters if type(f).__name__=='GlyphsFilterOffsetCurve'),None)
        if adapter is not None and callable(getattr(adapter,'filter',None)):
            # Check each master, both straight and curved counters and topology.
            trials=[]
            for mid in masters:
                for name in ('H','O'):
                    original=font.glyphs[name].layers[mid]
                    layer=original.copy(); before=helper['topology'](layer)
                    source_hash=helper['digest'](helper['layer_state'](original))
                    with precise(layer):adapter.filter(layer,False,{0:3.25,1:2.5,2:0,3:.5,4:'keep'})
                    assert before==helper['topology'](layer), 'Offset changed topology'
                    assert helper['digest'](helper['layer_state'](original))==source_hash
                    # Exact H extent and approximate curve extrema are separate evidence.
                    if name=='H':
                        ys=[n.position.y for p in layer.paths for n in p.nodes]
                        assert abs(max(ys)-min(ys)-705)<1e-6, 'Offset height mismatch'
                    trials.append(dict(glyph=name,master=mid,topologyPreserved=True))
            qualification=dict(build=str(Glyphs.buildNumber),adapter='layer-filter-keep')
            offset=dict(qualified=True,trials=trials,limits='Synthetic H/O fixtures; visual review and broader design qualification remain required')
    if offset is None:offset=dict(qualified=False,reason='No callable live layer-local Offset Curve instance; native UI handoff required')
    rows=[dict(source=n,kind=k,destination=('acutecomb.'+k if n=='acutecomb.case' else None))
          for k in ('sc','pc') for n in ('H','O','A','acutecomb.case','Aacute','Z')]
    settings={kind:{mid:dict(height=height,scaleX=.825,offsetX=3.25 if qualification else 0,
              offsetY=2.5 if qualification else 0,tracking=4.25) for mid in masters}
              for kind,height in [('sc',550),('pc',500)]}
    params=dict(stage='inspect',masters=masters,rows=rows,sets=settings,
                componentMap={kind:{'acutecomb.case':'acutecomb.'+kind} for kind in ('sc','pc')})
    if qualification:params['offsetQualification']=qualification
    before=run(font,params)
    params.update(stage='construct',identity=before['identity'],expected=before['guards'])
    result=run(font,params)
    assert len(result['created'])==10 and set(result['skipped'])=={'z.sc','z.pc'}
    for kind,height in [('sc',550),('pc',500)]:
        for mid in masters:
            layer=font.glyphs['h.'+kind].layers[mid]
            ys=[n.position.y for p in layer.paths for n in p.nodes]
            assert abs(min(ys))<1e-6 and abs(max(ys)-height)<1e-6
            assert not layer.temporarilyDisableRounding()
            assert not list(font.glyphs['h.'+kind].unicodes or [])
            assert font.glyphs['aacute.'+kind].layers[mid].components[0].componentName=='a.'+kind
            assert font.glyphs['aacute.'+kind].layers[mid].components[1].componentName=='acutecomb.'+kind
            # Inspect precise node coordinates, since native bounds can be grid-rounded.
            assert any(abs(n.position.x-round(n.position.x))>1e-6 for p in layer.paths for n in p.nodes)
    params.update(stage='verify',expected=result['resultGuards'])
    assert run(font,params)['changesVerified']
    manual=font.glyphs['h.sc'].layers[masters[0]]
    with precise(manual):manual.paths[0].nodes[0].position=(55.25,1.5)
    assert 'h.sc' in run(font,params)['changedSinceReview']
    params['stage']='inspect'; current=run(font,params)
    params.update(stage='construct',expected=current['guards'])
    again=run(font,params)
    assert not again['created'] and len(again['preserved'])==10
    assert abs(manual.paths[0].nodes[0].position.x-55.25)<1e-6
    # Also qualify an explicitly requested single-master subset without fabricating other masters.
    single=dict(params, stage='inspect',masters=masters[:1],rows=[dict(source='H',kind='sc',destination='h.subset.sc')])
    inspected=run(font,single);single.update(stage='construct',identity=inspected['identity'],expected=inspected['guards'])
    subset=run(font,single)
    assert subset['created']==['h.subset.sc'] and any('Unrequested masters' in x['reason'] for x in subset['needsReview'])
    report=dict(host=dict(version=str(Glyphs.versionString),build=str(Glyphs.buildNumber)),
        inventory=inventory,offset=offset,created=result['created'],skipped=result['skipped'],
        checks=['two-master straight and cubic outlines','both cap sets','anchors and derived composites',
                'source preservation','fractional coordinates','open-outline handoff',
                'manual-change detection','repeated construction preservation','single-master subset'],
        opticalApproval=False,interpolationSampling=False,featureShaping=False)
    return report


if __name__=='__main__':
    print(json.dumps(qualify(),ensure_ascii=False))
