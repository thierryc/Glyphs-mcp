"""Native-independent proposal selection and stroke-boundary measurements.

This module never edits a font. Feed it native expanded stroke outlines from
detached trials. Sampling bounds are conservative, not exact Hausdorff values.
"""
from __future__ import annotations

import heapq
import math


def _distance2(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = dx*dx+dy*dy
    t = max(0., min(1., ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0.
    return (p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2


def _curve(points, flatness, step, depth=0):
    a, b, c, d = points
    if max(_distance2(b, a, d), _distance2(c, a, d)) <= flatness**2 and math.dist(a, d) <= step:
        return [a, d]
    if depth >= 28:
        raise ValueError('curve sampling did not converge; hold the proposal')
    ab, bc, cd = [tuple((x+y)/2 for x, y in zip(p, q)) for p, q in ((a,b),(b,c),(c,d))]
    abc = tuple((x+y)/2 for x,y in zip(ab,bc))
    bcd = tuple((x+y)/2 for x,y in zip(bc,cd))
    middle = tuple((x+y)/2 for x,y in zip(abc,bcd))
    return _curve((a,ab,abc,middle),flatness,step,depth+1)[:-1]+_curve((middle,bcd,cd,d),flatness,step,depth+1)


def flatten(path, *, flatness=.002, step=.25):
    if not all(math.isfinite(x) and x > 0 for x in (flatness,step)):
        raise ValueError('positive finite sampling bounds required')
    nodes=path['nodes']; on=[i for i,n in enumerate(nodes) if n['type']!='offcurve']
    if len(on)<2:
        raise ValueError('unsupported outline')
    result=[]
    ends=on if path['closed'] else on[1:]
    for end in ends:
        indices=[end]; cursor=(end-1)%len(nodes)
        while nodes[cursor]['type']=='offcurve':
            indices.append(cursor); cursor=(cursor-1)%len(nodes)
            if cursor==end: raise ValueError('malformed outline')
        indices.append(cursor); indices.reverse()
        points=[(float(nodes[i]['x']),float(nodes[i]['y'])) for i in indices]
        if not all(math.isfinite(v) for p in points for v in p): raise ValueError('non-finite outline')
        if len(points)==2 and nodes[end]['type']=='line':
            a,b=points; count=max(1,math.ceil(math.dist(a,b)/step))
            sampled=[tuple(x+(y-x)*i/count for x,y in zip(a,b)) for i in range(count+1)]
        elif len(points)==4 and nodes[end]['type']=='curve':
            sampled=_curve(points,flatness,step)
        else: raise ValueError('only native expanded line/cubic outlines are qualified')
        result.extend(sampled if not result else sampled[1:])
    return result


def _box(segments):
    return (min(p[0] for s in segments for p in s),min(p[1] for s in segments for p in s),
            max(p[0] for s in segments for p in s),max(p[1] for s in segments for p in s))


def _tree(segments):
    box=_box(segments)
    if len(segments)<=8: return box,segments,None,None
    axis=int(box[3]-box[1]>box[2]-box[0])
    ordered=sorted(segments,key=lambda s:s[0][axis]+s[1][axis]); half=len(ordered)//2
    return box,None,_tree(ordered[:half]),_tree(ordered[half:])


def _box_distance(p,box):
    return max(box[0]-p[0],0,p[0]-box[2])**2+max(box[1]-p[1],0,p[1]-box[3])**2


def _nearest(p,tree):
    best=float('inf'); queue=[(0.,0,tree)]; serial=0
    while queue:
        lower,_,node=heapq.heappop(queue)
        if lower>=best: continue
        if node[1] is not None:
            best=min(best, *(_distance2(p,*segment) for segment in node[1]))
        else:
            for child in node[2:]:
                serial+=1; heapq.heappush(queue,(_box_distance(p,child[0]),serial,child))
    return math.sqrt(best)


def boundary_error(before,after, *, flatness=.002, step=.25):
    """Compare one native-expanded stroke; retain separate strokes at the caller."""
    if len(before)!=len(after) or not before:
        raise ValueError('expanded contour count changed or unavailable')
    maximum=0.
    for a,b in zip(before,after):
        if not a['closed'] or not b['closed']: raise ValueError('expanded outlines must be closed')
        pa,pb=flatten(a,flatness=flatness,step=step),flatten(b,flatness=flatness,step=step)
        area=lambda points:sum(x[0]*y[1]-x[1]*y[0] for x,y in zip(points,points[1:]))
        if area(pa)*area(pb)<=0: raise ValueError('contour winding/degeneracy changed')
        ta,tb=_tree(list(zip(pa,pa[1:]))),_tree(list(zip(pb,pb[1:])))
        maximum=max(maximum,max(_nearest(p,tb) for p in pa),max(_nearest(p,ta) for p in pb))
    return {'sampledBoundaryError':maximum,'boundaryErrorUpperBound':maximum+step/2+2*flatness,
            'samplingStep':step,'flatness':flatness}


def choose_removals(candidates, evaluate, budgets, *, required_cases, pinned=()):
    """Deterministic best-first trials, always measured against the ORIGINAL.

    evaluate(frozenset(ids)) returns case -> metric -> nonnegative measured error.
    Every requested metric must exist for every case. evaluate must include all
    affected masters and required native intermediate instances; do not sum or
    average their errors. Reject missing/failed native evaluation at the caller.
    """
    if not budgets or any(not math.isfinite(v) or v<0 for v in budgets.values()):
        raise ValueError('explicit finite nonnegative budgets required')
    remaining=set(candidates)-set(pinned); selected=frozenset(); history=[]
    while remaining:
        ready=[]
        for item in sorted(remaining):
            metrics=evaluate(selected|{item})
            if not metrics or set(metrics)!=set(required_cases): raise ValueError('native validation cases are missing or unexpected')
            scores=[]
            for case in metrics.values():
                for key,budget in budgets.items():
                    value=case[key]
                    if not math.isfinite(value) or value<0: raise ValueError('invalid measured error')
                    scores.append(value/budget if budget else 0. if value==0 else float('inf'))
            score=max(scores)
            if score<=1: ready.append((score,item,metrics))
        if not ready: break
        score,item,metrics=min(ready,key=lambda r:(r[0],r[1]))
        selected=selected|{item}; remaining.remove(item)
        history.append({'removed':item,'worstNormalizedError':score,'metrics':metrics})
    return {'removed':sorted(selected),'held':sorted(set(candidates)-selected),'history':history,
            'optimality':'greedy error-bounded selection; not a global minimum proof'}
