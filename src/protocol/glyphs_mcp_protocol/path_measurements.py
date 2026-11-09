"""Native-independent conservative boundary measurements.

This module never edits a font. Feed it native expanded stroke outlines from
detached trials. Sampling bounds are conservative, not exact Hausdorff values.
"""
from __future__ import annotations

import heapq
import math

MAX_MEASUREMENT_POINTS = 65536
MAX_TOPOLOGY_CELLS = 8192


def _distance2(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = dx*dx+dy*dy
    t = max(0., min(1., ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)) if length else 0.
    return (p[0]-a[0]-t*dx)**2+(p[1]-a[1]-t*dy)**2


def _curve(points, flatness, step, depth=0, remaining=None):
    if remaining is None: remaining=[MAX_MEASUREMENT_POINTS-1]
    a, b, c, d = points
    if max(_distance2(b, a, d), _distance2(c, a, d)) <= flatness**2 and math.dist(a, d) <= step:
        remaining[0]-=1
        if remaining[0]<0:raise ValueError('measurement exceeds the 65,536-point work limit; hold the proposal')
        return [a, d]
    if depth >= 28:
        raise ValueError('curve sampling did not converge; hold the proposal')
    ab, bc, cd = [tuple((x+y)/2 for x, y in zip(p, q)) for p, q in ((a,b),(b,c),(c,d))]
    abc = tuple((x+y)/2 for x,y in zip(ab,bc))
    bcd = tuple((x+y)/2 for x,y in zip(bc,cd))
    middle = tuple((x+y)/2 for x,y in zip(abc,bcd))
    return _curve((a,ab,abc,middle),flatness,step,depth+1,remaining)[:-1]+_curve((middle,bcd,cd,d),flatness,step,depth+1,remaining)


def flatten(path, *, flatness=.002, step=.25):
    if not all(math.isfinite(x) and x > 0 for x in (flatness,step)):
        raise ValueError('positive finite sampling bounds required')
    nodes=path['nodes']; on=[i for i,n in enumerate(nodes) if n['type']!='offcurve']
    if len(on)<2:
        raise ValueError('unsupported outline')
    result=[];remaining=[MAX_MEASUREMENT_POINTS-1]
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
            remaining[0]-=count
            if remaining[0]<0:raise ValueError('measurement exceeds the 65,536-point work limit; hold the proposal')
            sampled=[tuple(x+(y-x)*i/count for x,y in zip(a,b)) for i in range(count+1)]
        elif len(points)==4 and nodes[end]['type']=='curve':
            sampled=_curve(points,flatness,step,remaining=remaining)
        else: raise ValueError('only native expanded line/cubic outlines are qualified')
        result.extend(sampled if not result else sampled[1:])
    return result


def topology_cells(path, flatness):
    """Monotone Bézier pieces whose control hulls enclose the entire curve."""
    remaining=[MAX_TOPOLOGY_CELLS]
    def reserve():
        remaining[0]-=1
        if remaining[0]<0:raise ValueError('topology subdivision exceeds its work limit; hold the proposal')
    def split(points,depth=0):
        a,b,c,d=points;dx,dy=d[0]-a[0],d[1]-a[1];length=dx*dx+dy*dy
        projections=[(p[0]-a[0])*dx+(p[1]-a[1])*dy for p in points]
        monotone=length>0 and all(x<=y for x,y in zip(projections,projections[1:]))
        if monotone and max(_distance2(b,a,d),_distance2(c,a,d))<=flatness**2:
            reserve();return [points]
        if depth>=24:raise ValueError('unresolved curve monotonicity')
        ab,bc,cd=[tuple((x+y)/2 for x,y in zip(p,q)) for p,q in ((a,b),(b,c),(c,d))]
        abc=tuple((x+y)/2 for x,y in zip(ab,bc));bcd=tuple((x+y)/2 for x,y in zip(bc,cd))
        middle=tuple((x+y)/2 for x,y in zip(abc,bcd))
        return split((a,ab,abc,middle),depth+1)+split((middle,bcd,cd,d),depth+1)
    nodes=path['nodes'];on=[i for i,n in enumerate(nodes) if n['type']!='offcurve'];result=[]
    for end in on if path['closed'] else on[1:]:
        indices=[end];cursor=(end-1)%len(nodes)
        while nodes[cursor]['type']=='offcurve':
            indices.append(cursor);cursor=(cursor-1)%len(nodes)
            if cursor==end:raise ValueError('malformed outline')
        indices.append(cursor);indices.reverse()
        points=tuple((float(nodes[i]['x']),float(nodes[i]['y'])) for i in indices)
        if len(points)==2 and nodes[end]['type']=='line':
            if points[0]!=points[1]:reserve();result.append(points)
        elif len(points)==4 and nodes[end]['type']=='curve':result.extend(split(points))
        else:raise ValueError('unsupported topology segment')
    if len(result)<2:raise ValueError('degenerate outline')
    return result


def separated_hulls(left,right,join=None):
    """A separating projection certifies disjoint convex control hulls.

    Adjacent pieces must lie strictly on opposite sides of a line through their
    shared endpoint. Failure to find a certificate holds, including tangencies.
    """
    from itertools import combinations
    axes=[(1.,0.),(0.,1.)]
    for points in (left,right):
        for a,b in combinations(points,2):
            dx,dy=b[0]-a[0],b[1]-a[1]
            axes.extend(((dx,dy),(-dy,dx)))
    if join is not None:
        incoming=next((p for p in reversed(left[:-1]) if p!=join),None)
        outgoing=next((p for p in right[1:] if p!=join),None)
        if incoming is None or outgoing is None:return False
        a=(join[0]-incoming[0],join[1]-incoming[1]);b=(outgoing[0]-join[0],outgoing[1]-join[1])
        la,lb=math.hypot(*a),math.hypot(*b)
        axes.append((a[0]/la+b[0]/lb,a[1]/la+b[1]/lb))
    scale=max(1.,*(abs(v) for p in left+right for v in p));epsilon=scale*1e-12
    for x,y in axes:
        length=math.hypot(x,y)
        if not length:continue
        x,y=x/length,y/length
        if join is None:
            a=[p[0]*x+p[1]*y for p in left];b=[p[0]*x+p[1]*y for p in right]
            if max(a)+epsilon<min(b) or max(b)+epsilon<min(a):return True
        else:
            a=[(p[0]-join[0])*x+(p[1]-join[1])*y for p in left if p!=join]
            b=[(p[0]-join[0])*x+(p[1]-join[1])*y for p in right if p!=join]
            if max(a)<-epsilon and min(b)>epsilon or max(b)<-epsilon and min(a)>epsilon:return True
    return False


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

