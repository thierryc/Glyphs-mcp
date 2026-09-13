"""External native slant with optional, tested straight-stem preservation."""

import json
import math

from glyphs_mcp_protocol.coordinates import topology_hash
from .spacing import exact_copy
from .spacing_job import layer_hash
from .straight_stems import compensate_stems
from .worker import WorkerError


def _fail(code, action, **target):
    location={k:v if isinstance(v,int) else str(v)[:160] for k,v in target.items()}
    raise WorkerError('slant.'+code+': '+json.dumps(location,ensure_ascii=False)+'. '+action)


def validate_options(raw):
    defaults={'angle':12.0,'pivotY':0.0,'preserveStraightStems':False,'masters':[]}
    if not isinstance(raw,dict) or set(raw)-set(defaults):raise ValueError('unknown slant options')
    options={**defaults,**raw}
    for key,limit in (('angle',30),('pivotY',10000)):
        v=options[key]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>limit:raise ValueError('invalid '+key)
    if options['angle']==0:raise ValueError('slant angle must be nonzero')
    if not isinstance(options['preserveStraightStems'],bool):raise ValueError('preserveStraightStems must be boolean')
    ids=options['masters']
    if not isinstance(ids,list) or len(ids)>100 or any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):raise ValueError('invalid master IDs')
    return options


def paths(layer):
    return [{'closed':bool(p.closed),'nodes':[{'x':float(n.position.x),'y':float(n.position.y),'type':str(n.type),'smooth':bool(n.smooth)} for n in p.nodes]} for p in layer.paths]


def multiply(a,b):
    """Affine composition a after b, including translations."""
    return [a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],
            a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5]]


def prepare(font,request):
    options=validate_options(request.get('options',{}));names=set(request.get('glyphs') or [])
    glyphs=[g for g in font.glyphs if not names or str(g.name) in names]
    missing=names-{str(g.name) for g in glyphs}
    if missing:
        _fail('missing_glyph','Choose glyphs present in the saved source; a missing glyph does not require document discovery.',
              glyph=sorted(missing)[0],missingCount=len(missing))
    mids={str(m.id) for m in font.masters if not options['masters'] or str(m.id) in options['masters']}
    if not mids or options['masters'] and mids!=set(options['masters']):
        missing=sorted(set(options['masters'])-mids)
        _fail('missing_master','Choose an exact ordinary master ID present in the saved source.',
              master=missing[0] if missing else '',missingCount=len(missing))
    selected={(str(g.name),str(l.layerId)) for g in glyphs for l in g.layers if str(l.layerId)==str(l.associatedMasterId) and str(l.layerId) in mids
              and not any(bool(c.automaticAlignment) for c in l.components)}
    tangent=math.tan(math.radians(options['angle']));offset=-tangent*options['pivotY']
    shear=[1,0,tangent,1,offset,0];inverse=[1,0,-tangent,1,-offset,0]
    changes,rows=[],[]
    for glyph in glyphs:
        for layer in glyph.layers:
            mid=str(layer.layerId)
            if mid!=str(layer.associatedMasterId) or mid not in mids:continue
            row={'glyph':str(glyph.name),'layer':mid,'width':float(layer.width)}
            if (str(glyph.name),mid) not in selected:
                rows.append(dict(row,status='skipped',reason='automatic_component_alignment'));continue
            source_paths=paths(layer);candidate=exact_copy(layer)
            candidate.slantX_origin_doCorrection_checkSelection_(options['angle'],options['pivotY'],False,False)
            raw_paths=paths(candidate)
            diagnostics={'compensatedPairCount':0,'skippedPairs':[]}
            if options['preserveStraightStems']:
                result=compensate_stems(source_paths,raw_paths,strength=1.0,upm=float(font.upm))
                diagnostics=result['diagnostics']
                for path,data in zip(candidate.paths,result['paths']):
                    for node,point in zip(path.nodes,data['nodes']):node.position=(point['x'],point['y'])
            # A selected component base is already slanted. Conjugation avoids
            # applying the shear twice; unselected bases receive the full shear.
            for ci,(original,component) in enumerate(zip(layer.components,candidate.components)):
                original_matrix=list(original.transform)
                component.transform=tuple(original_matrix)
                if list(component.transform)!=original_matrix:
                    _fail('unsupported_component_transform','The native component transform cannot round-trip exactly; inspect this component in Glyphs. No applicable slant patch was prepared.',
                          glyph=glyph.name,layer=mid,component=ci,reference=original.componentName,stage='source')
                composed=multiply(shear,original_matrix)
                base_mid=str(getattr(original,'componentMasterId',None) or mid)
                if (str(original.componentName),base_mid) in selected:composed=multiply(composed,inverse)
                component.transform=tuple(composed)
                retained=list(component.transform)
                component.transform=tuple(retained)
                if any(not math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-9) for a,b in zip(retained,composed)) or list(component.transform)!=retained:
                    _fail('unsupported_component_transform','The native component transform cannot round-trip exactly; inspect this component in Glyphs. No applicable slant patch was prepared.',
                          glyph=glyph.name,layer=mid,component=ci,reference=original.componentName,stage='slanted')
            change={'kind':'coordinates','glyph':str(glyph.name),'layer':mid,'nodes':[],'anchors':[],'components':[],'before':[],'after':[]}
            def add(key,target,before,after):
                before,after=list(before),list(after)
                if before!=after:
                    change[key].append(target);change['before'].append(before);change['after'].append(after)
            for pi,(original,path) in enumerate(zip(layer.paths,candidate.paths)):
                for ni,(before,after) in enumerate(zip(original.nodes,path.nodes)):add('nodes',[pi,ni],before.position,after.position)
            for anchor in layer.anchors:add('anchors',str(anchor.name),anchor.position,candidate.anchors[anchor.name].position)
            for ci,(before,after) in enumerate(zip(layer.components,candidate.components)):add('components',ci,before.transform,after.transform)
            change['topologyHash']=topology_hash([[bool(p.closed),[str(n.type) for n in p.nodes]] for p in layer.paths],
                [str(a.name) for a in layer.anchors],[[str(c.componentName),bool(c.automaticAlignment)] for c in layer.components])
            if change['before']:changes.append(change)
            rows.append(dict(row,status='suggested' if change['before'] else 'unchanged',beforeHash=layer_hash(layer),afterHash=layer_hash(candidate),
                correction=diagnostics,angle=options['angle'],pivotY=options['pivotY'],preserveStraightStems=options['preserveStraightStems']))
    return changes,{'kind':'slant','layers':rows,'claim':'Mechanical slant with optional preservation of accepted straight-stem widths; curved stems and automatic component layers are outside correction scope.'}
