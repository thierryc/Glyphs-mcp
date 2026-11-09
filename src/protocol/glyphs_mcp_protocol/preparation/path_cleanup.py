"""Deterministic coordinated cleanup on detached native layers only."""
import math
from copy import deepcopy
from itertools import combinations
from ..path_cleanup import validate_options, BOUNDED
from ..path_doctor import duplicate_indices, qualify_duplicates, seam_pattern, qualify
from ..outline import path_hash, outline_state_hash
from ..path_measurements import boundary_error, flatten
from . import stored_layers
from .path_doctor import path_state, validate_segments, referenced
from .outline import _value, _copy, _compare, _shape_state, _apply, _glyph


def groups(font, glyph):
    """Native flags and axis rules select branches. Unknown specials fail closed."""
    masters = {str(m.id) for m in font.masters}
    result = {'default': []}
    for layer in stored_layers(glyph):
        identity = str(layer.layerId)
        if identity in masters or _value(layer, 'isBraceLayer', False):
            result['default'].append(layer)
        elif _value(layer, 'isBracketLayer', False):
            rules = _value(layer, 'attributes', {}).get('axisRules')
            if rules is None: raise ValueError('bracket layer has unavailable native axis rules')
            # Full native rules, not a layer name or associated-master guess.
            from .path_attributes import plain
            import json
            key = json.dumps(plain(rules), sort_keys=True)
            result.setdefault(key, []).append(layer)
        elif _value(layer, 'isSpecialLayer', False):
            raise ValueError('unsupported special interpolation layer')
    if {str(l.layerId) for l in result['default']} & masters != masters:
        raise ValueError('missing ordinary master layers')
    for key, layers in result.items():
        if key != 'default' and {str(_value(l, 'associatedMasterId', '')) for l in layers} != masters:
            raise ValueError('bracket branch lacks explicit layers for every master')
        if not layers or len({_compare(l) for l in layers}) != 1:
            raise ValueError('interpolation branch is already incompatible')
    return result



def layer_context(layer):
    from .path_attributes import state
    def point(owner):
        p=owner.position
        return (float(p.x),float(p.y))
    return {'width':float(layer.width),
            'metrics':[str(_value(layer,k,None)) for k in ('leftMetricsKey','rightMetricsKey','widthMetricsKey')],
            'anchors':[(str(_value(a,'name','')),point(a)) for a in _value(layer,'anchors',[])],
            'components':[s for s in _shape_state(layer) if s['kind']=='component'],
            'attributes':state(layer)}

def protected(state):
    attrs = state['attributeState']
    return (state.get('locked') or attrs.get('userData') or
            any(n.get('name') or n['attributeState'].get('attributes') or n['attributeState'].get('userData') for n in state['nodes']))


def stroked(state):
    attrs = state['attributeState'].get('attributes', {})
    return any(k in attrs for k in ('strokeWidth', 'strokeHeight')) or any(
        n['attributeState'].get('attributes', {}).get('penPoints') for n in state['nodes'])


def candidates(state, options):
    nodes = state['nodes']; enabled = options['operations']
    if 'duplicates' in enabled and duplicate_indices(state):
        yield 'duplicates', {'op':'remove_consecutive_duplicate_nodes'}
    if 'seams' in enabled and seam_pattern(state):
        yield 'seams', {'op':'normalize_closed_seam'}
    if protected(state) or stroked(state): return
    for i in range(1, len(nodes)-1):
        a,b,c = nodes[i-1:i+2]
        if 'collinear' in enabled and b['type'] == c['type'] == 'line' and a['type'] != 'offcurve':
            ab=(b['x']-a['x'],b['y']-a['y']);bc=(c['x']-b['x'],c['y']-b['y'])
            if ab[0]*bc[1] == ab[1]*bc[0] and ab[0]*bc[0]+ab[1]*bc[1] > 0:
                yield 'collinear', {'op':'delete_nodes','nodes':[i]}
        if b['type'] != 'offcurve' and b.get('smooth'):
            if 'near_nodes' in enabled and a['type'] != 'offcurve' and 0 < math.hypot(b['x']-a['x'], b['y']-a['y']) <= options['maxDeviation']:
                yield 'near_nodes', {'op':'remove_node','node':i}
            if 'simplify_curves' in enabled and b['type'] == 'curve':
                yield 'simplify_curves', {'op':'remove_node','node':i}
    if 'align_handles' in enabled:
        for i,n in enumerate(nodes):
            if n['type'] != 'offcurve': continue
            adjacent = [(i-1)%len(nodes), (i+1)%len(nodes)]
            owners = [j for j in adjacent if nodes[j]['type'] != 'offcurve' and nodes[j].get('smooth')]
            if len(owners) != 1: continue
            owner=nodes[owners[0]];dx=n['x']-owner['x'];dy=n['y']-owner['y']
            if not dx or not dy: continue
            angle=math.degrees(math.atan2(abs(dy),abs(dx)))
            if min(angle,90-angle) <= options['angleTolerance']:
                position={'x':n['x'] if angle<45 else owner['x'], 'y':owner['y'] if angle<45 else n['y']}
                yield 'align_handles', {'op':'update_nodes','updates':[{'index':i,'position':position}]}


def topology(states, tolerance):
    """Certify simple, separate contours using enclosing Bézier control hulls."""
    from ..path_measurements import topology_cells, separated_hulls
    contours=[topology_cells(s,tolerance) for s in states]
    def box(cell):
        return (min(p[0] for p in cell),min(p[1] for p in cell),
                max(p[0] for p in cell),max(p[1] for p in cell))
    cells=[(j,i,cell,box(cell)) for j,contour in enumerate(contours) for i,cell in enumerate(contour)]
    # Sweep control-hull bounds on x. A box separation is a valid convex-hull
    # certificate; only overlapping boxes need the more expensive projections.
    epsilon=max(1.,*(abs(v) for _,_,_,bounds in cells for v in bounds))*1e-12
    active=[]
    for ordinal,right_entry in sorted(enumerate(cells),key=lambda entry:entry[1][3][0]):
        rb=right_entry[3]
        active=[entry for entry in active if entry[1][3][2]+epsilon>=rb[0]]
        for old,left_entry in active:
            lb=left_entry[3]
            if lb[3]+epsilon<rb[1] or rb[3]+epsilon<lb[1]:continue
            first,second=(left_entry,right_entry) if old<ordinal else (right_entry,left_entry)
            j,i,left,_=first;k,h,right,_=second
            adjacent=j==k and (h==i+1 or i==0 and h==len(contours[j])-1)
            if adjacent:
                a,b=(right,left) if i==0 and h==len(contours[j])-1 else (left,right)
                if a[-1]!=b[0] or not separated_hulls(a,b,a[-1]):
                    raise ValueError('intersection or ambiguous adjacent contour clearance')
            elif not separated_hulls(left,right):
                raise ValueError('intersection or ambiguous contour clearance')
        active.append((ordinal,right_entry))
    loops=[flatten(s,flatness=tolerance,step=max(.25,tolerance*16)) for s in states]
    def inside(p, loop):
        x,y=p;hit=False
        for a,b in zip(loop,loop[1:]):
            if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:hit=not hit
        return hit
    return [[inside(p[0],q) for k,q in enumerate(loops) if k!=j] for j,p in enumerate(loops)]


def validate_bounded(original, trial, budget):
    if any(stroked(s) or not s['closed'] for s in original+trial):
        raise ValueError('bounded edits require closed filled outlines without Pen profiles')
    flatness=min(.002,budget/32);step=min(.25,budget/4)
    if topology(original,flatness)!=topology(trial,flatness):raise ValueError('contour nesting changed')
    evidence=boundary_error(original,trial,flatness=flatness,step=step)
    if evidence['boundaryErrorUpperBound']>budget:raise ValueError('cumulative deviation budget exceeded')
    return evidence


def validate_effect(before, after, operation):
    """Native fitting may move handles, but may not rewrite authored semantics."""
    if {k:v for k,v in before.items() if k!='nodes'}!={k:v for k,v in after.items() if k!='nodes'}:
        raise ValueError('native cleanup changed path attributes or direction flags')
    removed=set(operation.get('removedNodes',operation.get('nodes',[])))
    if 0 in removed:raise ValueError('native cleanup removed the contour start')
    if operation['op']=='remove_node' and any(before['nodes'][i]['type']!='offcurve' and i!=operation['node'] for i in removed):
        raise ValueError('native removal removed another on-curve node')
    surviving=[node for i,node in enumerate(before['nodes']) if i not in removed]
    if len(surviving)!=len(after['nodes']):raise ValueError('unexpected native topology change')
    for old,new in zip(surviving,after['nodes']):
        if {k:v for k,v in old.items() if k not in ('x','y')}!={k:v for k,v in new.items() if k not in ('x','y')}:
            raise ValueError('native cleanup changed surviving node semantics')
        if operation['op']=='delete_nodes' and old!=new:
            raise ValueError('exact line removal changed a surviving coordinate')


def prepare_iter(font, request, *, sample_validator=None):
    options=validate_options(request['options']);changes=[];rows=[];held=[];examined=0
    if sample_validator is None:
        from .path_cleanup_samples import make_validator
        sample_validator=make_validator()
    glyphs=list(font.glyphs) if options['glyphs']=='all' else [_glyph(font,n) for n in options['glyphs']]
    for glyph in glyphs:
        name=str(glyph.name)
        try:
            if _value(glyph,'locked',False):raise ValueError('glyph is locked')
            branches=groups(font,glyph)
        except (ValueError,RuntimeError,TypeError) as exc:
            held.append({'glyph':name,'reason':str(exc)});yield;continue
        for branch,layers in branches.items():
            examined+=len(layers)
            originals=[_copy(l) for l in layers];working=[_copy(l) for l in layers]
            operations=[[] for l in layers];measurements=[[] for l in layers]
            for path_index in range(len(working[0].paths)):
                # Recompute after each accepted removal; deterministic order.
                while True:
                    accepted=False
                    source=path_state(working[0].paths[path_index])
                    if stroked(source) and any(op in BOUNDED for op in options['operations']):
                        entry={'glyph':name,'branch':branch,'path':path_index,'reason':'bounded stroke/Pen-profile optimization is outside this cleanup pass'}
                        if entry not in held:held.append(entry)
                    for kind,op in candidates(source,options):
                        trials=[_copy(l) for l in working];resolved=[];errors=[]
                        try:
                            for index,(live,trial) in enumerate(zip(layers,trials)):
                                path=trial.paths[path_index];state=path_state(path)
                                if _value(live,'locked',False) or referenced(live,live.paths[path_index]):raise ValueError('locked or hinted layer/path')
                                def address(value):
                                    return (value.get('node'), tuple(value.get('nodes', [])),
                                            tuple(u['index'] for u in value.get('updates', [])))
                                matched=[candidate for k,candidate in candidates(state,options)
                                         if k==kind and address(candidate)==address(op)]
                                if not matched:raise ValueError('candidate does not qualify in every layer')
                                operation={**deepcopy(matched[0]),'path':path_index}
                                if kind in ('duplicates','seams'):
                                    operation['stateHash']=path_hash(state)
                                    # Different redundant runs would change correspondence.
                                    if kind=='duplicates' and duplicate_indices(state)!=duplicate_indices(source):raise ValueError('duplicate correspondence differs')
                                context=layer_context(trial)
                                other_paths=[path_state(p) for p in trial.paths]
                                item,_,_=_apply(trial,operation);resolved.append(item)
                                if layer_context(trial)!=context:raise ValueError('cleanup changed unrelated layer data')
                                if len(trial.paths)!=len(other_paths) or any(path_state(p)!=old for j,(p,old) in enumerate(zip(trial.paths,other_paths)) if j!=path_index):
                                    raise ValueError('cleanup changed an unrelated contour')
                                if kind not in ('duplicates','seams'):
                                    validate_effect(state,path_state(trial.paths[path_index]),item)
                                if kind=='collinear':
                                    i=operation['nodes'][0]
                                    def ratio(st):
                                        a,b,c=st['nodes'][i-1:i+2]
                                        axis='x' if c['x']!=a['x'] else 'y'
                                        return (b[axis]-a[axis])/(c[axis]-a[axis])
                                    if ratio(state)!=ratio(source):raise ValueError('collinear node has different interpolation parameter')
                                if kind in BOUNDED:
                                    errors.append(validate_bounded([path_state(p) for p in originals[index].paths], [path_state(p) for p in trial.paths],options['maxDeviation']))
                            if len({_compare(l) for l in trials})!=1:raise ValueError('candidate changes master correspondence')
                            if kind in BOUNDED:
                                if sample_validator is None:raise ValueError('native intermediate validation is unavailable')
                                samples=sample_validator(font,glyph,layers,trials,options)
                            for index,item in enumerate(resolved):
                                operations[index].append(item)
                                if kind in BOUNDED:measurements[index].append({'operation':kind,**errors[index],'intermediateSamples':samples})
                            working=trials;accepted=True;break
                        except (ValueError,RuntimeError,TypeError) as exc:
                            entry={'glyph':name,'branch':branch,'path':path_index,'operation':kind,'reason':str(exc)}
                            if entry not in held:held.append(entry)
                        yield
                    if not accepted:break
                yield
            if any(operations):
                try:
                    mode='bounded' if any(measurements) else 'exact'
                    samples=sample_validator(font,glyph,layers,working,{**options,'validationMode':mode})
                    for evidence in measurements:evidence.append({'operation':'final_'+mode+'_validation','intermediateSamples':samples})
                except (ValueError,RuntimeError,TypeError) as exc:
                    held.append({'glyph':name,'branch':branch,'reason':str(exc)})
                    yield;continue
            for live,original,trial,ops,evidence in zip(layers,originals,working,operations,measurements):
                if not ops:continue
                before=outline_state_hash(_shape_state(original));after=outline_state_hash(_shape_state(trial))
                changes.append({'kind':'outline','glyph':name,'layer':str(live.layerId),'beforeHash':before,'afterHash':after,'operations':ops})
                rows.append({'glyph':name,'layer':str(live.layerId),'status':'changed','removedNodes':sum(len(p.nodes) for p in original.paths)-sum(len(p.nodes) for p in trial.paths),'operationCount':len(ops),'measurements':evidence})
                yield
        yield
    return changes,{'claim':'Deterministic cleanup prepared on detached layers; no live edits or save.',
        'layers':rows,'held':held,'warnings':[f'{len(held)} cleanup candidates or glyphs held'] if held else [],
        'kind':'path_cleanup','settings':options,'changedLayers':len(changes),
        'unchangedLayers':examined-len(changes),'heldCount':len(held),
        'removedNodes':sum(row['removedNodes'] for row in rows),
        'validation':'All affected authored layers; native compatibility; bounded samples include authored locations, export instances, pairwise midpoints and both bracket-boundary sides. Sampled coverage is not a continuous designspace guarantee.',
        'comparison':'View → Changes Against Reference; Edit → Comparison Reference → Last Saved. Saving advances the reference.'}
