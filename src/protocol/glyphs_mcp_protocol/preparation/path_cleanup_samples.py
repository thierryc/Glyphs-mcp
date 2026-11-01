"""Native interpolation of isolated glyph copies, never the editable font."""
import math
from itertools import combinations
from .outline import _value
from .path_doctor import path_state


def exact_geometry(paths):
    """Canonical real segments and their endpoint profiles, for exact samples.

    Zero LINEs carry no geometry. Collinear LINE subdivisions carry no geometry
    when their removed endpoint has no profile. Preserve real cubic controls,
    native endpoint profile semantics, contour order and winding.
    """
    from .outline import _segment
    import json
    result=[]
    for path in paths:
        nodes=path['nodes'];ends=[i for i,n in enumerate(nodes) if n['type']!='offcurve']
        segments=[]
        for end in ends if path['closed'] else ends[1:]:
            kind,_,points=_segment(path,end)
            points=[tuple(p) for p in points]
            attrs=nodes[end]['attributeState']
            if kind=='line' and points[0]==points[-1]:continue
            segments.append([kind,points,attrs])
        changed=True
        while changed and len(segments)>1:
            changed=False
            for i in range(len(segments) if path['closed'] else len(segments)-1):
                j=(i+1)%len(segments);left,right=segments[i],segments[j]
                if left[0]!='line' or right[0]!='line' or left[2].get('attributes') or left[2].get('userData'):continue
                a,b=left[1];b2,c=right[1]
                ab=(b[0]-a[0],b[1]-a[1]);bc=(c[0]-b[0],c[1]-b[1])
                if b!=b2 or ab[0]*bc[1]!=ab[1]*bc[0] or ab[0]*bc[0]+ab[1]*bc[1]<=0:continue
                merged=['line',[a,c],right[2]]
                if j==0:segments=[merged]+segments[1:i]
                else:segments[i:j+1]=[merged]
                changed=True;break
        if path['closed'] and segments:
            key=lambda s:json.dumps(s,sort_keys=True)
            index=min(range(len(segments)),key=lambda i:key(segments[i:]+segments[:i]))
            segments=segments[index:]+segments[:index]
        result.append({'closed':path['closed'],'attributes':path['attributeState'],'segments':segments})
    return result


def locations(font, layers, boundary_layers=()):
    points={tuple(float(v) for v in m.axes) for m in font.masters}
    for layer in layers:
        if _value(layer,'isBraceLayer',False):
            coords=_value(layer,'attributes',{}).get('coordinates')
            if coords is None:raise ValueError('intermediate coordinates unavailable')
            if hasattr(coords, 'items'):
                base=next((list(m.axes) for m in font.masters if str(m.id)==str(layer.associatedMasterId)),None)
                if base is None:raise ValueError('intermediate master association unavailable')
                for key,value in coords.items():
                    index=int(key)
                    if index<0 or index>=len(base):raise ValueError('unsupported intermediate coordinate index')
                    base[index]=float(value)
                points.add(tuple(float(v) for v in base))
            else:
                points.add(tuple(float(v) for v in coords))
    authored=sorted(points)
    points.update(tuple((a+b)/2 for a,b in zip(left,right)) for left,right in combinations(authored,2))
    for instance in font.instances:
        if _value(instance,'exports',False):points.add(tuple(float(v) for v in instance.axes))
    # Evaluate both branch models on either side of every applicable boundary.
    # Extra samples outside a branch are conservative; this is not continuous
    # designspace certification or normalization of sparse bracket branches.
    seeds=sorted(points)
    for layer in boundary_layers:
        if not _value(layer,'isBracketLayer',False):continue
        rules=_value(layer,'attributes',{}).get('axisRules')
        if not isinstance(rules,(list,tuple)):
            from .path_attributes import plain
            rules=plain(rules)
        if not isinstance(rules,list):raise ValueError('unsupported bracket boundary rules')
        for index,rule in enumerate(rules):
            if index>=len(font.axes):raise ValueError('unsupported bracket axis')
            if not rule:continue
            low=min(p[index] for p in seeds);high=max(p[index] for p in seeds)
            epsilon=max(1e-6,(high-low)*1e-7)
            for field in ('min','max'):
                if field not in rule:continue
                value=rule[field]
                try:edge=float.fromhex(value['float']) if isinstance(value,dict) and set(value)=={'float'} else float(value)
                except (TypeError,ValueError) as exc:raise ValueError('unsupported bracket boundary value') from exc
                if not math.isfinite(edge):raise ValueError('invalid bracket boundary')
                for value in (edge-epsilon,edge,edge+epsilon):
                    if low<=value<=high:
                        for seed in seeds:
                            point=list(seed);point[index]=value;points.add(tuple(point))
    if any(len(p)!=len(font.axes) or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError('invalid interpolation coordinates')
    return sorted(points)


def isolated(font, glyph, layers, *, bracket=False, template=None):
    result=(template or font).copy()
    result.glyphs=[]
    clone=glyph.copy()
    if any(len(list(l.components)) for l in layers):
        raise ValueError('component-dependent interpolation needs separate qualification')
    # A complete bracket branch is evaluated as its own master family.
    branch=bracket
    selected=[]
    for layer in layers:
        copy=layer.copy()
        if branch:
            copy.layerId=str(layer.associatedMasterId)
            attrs=dict(copy.attributes);attrs.pop('axisRules',None);copy.pyobjc_instanceMethods.setAttributes_(attrs)
        selected.append(copy)
    clone.layers=selected
    result.glyphs.append(clone)
    return result


def make_validator():
    template=None
    def check(font,glyph,layers,trials,options):
        nonlocal template
        if template is None:
            template=font.copy();template.glyphs=[]
        return validate(font,glyph,layers,trials,options,template=template)
    return check


def validate(font,glyph,layers,trials,options,*,template=None):
    from GlyphsApp import GSInstance
    from .path_cleanup import validate_bounded
    bracket=all(_value(l,'isBracketLayer',False) for l in layers)
    before=isolated(font,glyph,layers,bracket=bracket,template=template);after=isolated(font,glyph,trials,bracket=bracket,template=template)
    reports=[]
    for axes in locations(font,layers,glyph.layers):
        states=[]
        for source in (before,after):
            instance=GSInstance();instance.font=source;instance.axes=list(axes)
            interpolated=instance.interpolatedFontProxy
            target=interpolated.glyphs[str(glyph.name)]
            if target is None:raise ValueError('native interpolation omitted glyph')
            states.append([path_state(p) for p in target.layers[0].paths])
        try:
            if options.get('validationMode')=='exact':
                if exact_geometry(states[0])!=exact_geometry(states[1]):
                    raise ValueError('exact sampled geometry/profile correspondence changed')
                evidence={'exactRealSegmentsAndProfiles':True}
            else:
                evidence=validate_bounded(states[0],states[1],options['maxDeviation'])
        except ValueError as exc:
            raise ValueError('native interpolation sample '+str(axes)+': '+str(exc)) from exc
        reports.append({'axes':list(axes),**evidence})
    return reports
