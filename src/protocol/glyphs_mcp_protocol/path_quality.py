"""Read-only line/cubic quality evidence, never an automatic repair policy."""
import math


def cross(a,b): return a[0]*b[1]-a[1]*b[0]
def sub(a,b): return (a[0]-b[0],a[1]-b[1])
def mul(a,t): return (a[0]*t,a[1]*t)
def add(a,b): return (a[0]+b[0],a[1]+b[1])


def roots(a,b,c):
    scale=max(abs(a),abs(b),abs(c),1e-300)
    a,b,c=a/scale,b/scale,c/scale
    if abs(a)<1e-14: return [] if abs(b)<1e-14 else [-c/b]
    discriminant=b*b-4*a*c
    if discriminant<0:return []
    q=-.5*(b+math.copysign(math.sqrt(discriminant),b))
    return [-b/(2*a)] if q==0 else sorted(set((q/a,c/q)))


def coefficients(points):
    a,b,c,d=points
    return a,mul(sub(b,a),3),mul(add(sub(c,mul(b,2)),a),3),sub(add(d,mul(b,3)),add(mul(c,3),a))


def segments(state):
    from .preparation.outline import _segment
    on=[i for i,n in enumerate(state['nodes']) if n['type']!='offcurve']
    for end in on if state['closed'] else on[1:]:
        kind,start,points=_segment(state,end)
        if kind not in ('line','curve'):raise ValueError('quality analysis supports line/cubic segments only')
        yield kind,start,end,points


def signed_area(state):
    # Integral (x dy - y dx)/2, exact polynomial integration for LINE/cubic.
    area=0.
    for kind,_,_,points in segments(state):
        if kind=='line':area+=cross(*points)/2;continue
        coeff=coefficients(points)
        area+=sum(j*cross(a,b)/(i+j) for i,a in enumerate(coeff) for j,b in enumerate(coeff) if j)/2
    return area


def is_stroke(state):
    attrs=state['attributeState'].get('attributes',{})
    return any(k in attrs for k in ('strokeWidth','strokeHeight')) or any(
        n['attributeState'].get('attributes',{}).get('penPoints') for n in state['nodes'])


def path_findings(state):
    """Yield (code, classification, severity, evidence, confidence, nodes)."""
    if is_stroke(state):return
    nodes=state['nodes']
    if len(nodes)>512:
        yield 'quality_analysis_held','unsupported','info',{'reason':'quality analysis is bounded to 512 stored points'},'definite',[]
        return
    if any(n['type']=='qcurve' for n in nodes):
        yield 'quality_analysis_held','unsupported','info',{'reason':'quadratic quality analysis requires separate qualification'},'definite',[]
        return
    if state['closed'] and len(nodes)>=12 and all(n['type']=='line' for n in nodes):
        yield 'polygon_fitting_candidate','optimization_candidate','info',{
            'nodeCount':len(nodes),'action':'Explicit path_fitting reconstruction; preserve intentional corners and review measured deviation. Corner flags alone do not create curves.'},'candidate',[]
    for kind,start,end,points in segments(state):
        if kind!='curve':continue
        a,b,c,d=points; left,right=sub(b,a),sub(c,d)
        if b==a or c==d:
            yield 'zero_handle','structural','warning',{'startNode':start,'endNode':end,
                'zeroAtStart':b==a,'zeroAtEnd':c==d,'action':'Inspect and qualify handle extraction separately; node duplication cleanup does not repair handles.'},'definite',[start,end]
        denominator=cross(left,right)
        scale=max(1.,math.hypot(*left)*math.hypot(*right))
        if abs(denominator)>scale*1e-12:
            t=cross(sub(d,a),right)/denominator;u=cross(sub(d,a),left)/denominator
            # Parallel/inflecting tangent configurations have no enclosing
            # forward triangle and are not automatically invalid.
            if t>0 and u>0:
                if t<1-1e-10 or u<1-1e-10:
                    yield 'handle_triangle_violation','suspicious','warning',{
                        'startHandleRatio':1/t,'endHandleRatio':1/u,
                        'action':'Review handles extending past their forward tangent intersection.'},'suspicious',[start,end]
                elif abs(1/t-1/u)>.2:
                    yield 'handle_balance_candidate','optimization_candidate','info',{
                        'startHandleRatio':1/t,'endHandleRatio':1/u,
                        'action':'Review intentional asymmetry and cross-master distribution; use Curve Inspector for eligible balancing.'},'candidate',[start,end]
        _,C,B,A=coefficients(points)
        extrema=[]
        for axis in range(2):
            extrema.extend({'axis':'xy'[axis],'t':t} for t in roots(3*A[axis],2*B[axis],C[axis]) if 1e-7<t<1-1e-7)
        if extrema:
            yield 'interior_extrema','optimization_candidate','info',{'events':extrema,
                'action':'Review add_extremes with force=false; avoid shallow segments and preserve master correspondence.'},'candidate',[start,end]
        inflections=[t for t in roots(3*cross(B,A),3*cross(C,A),cross(C,B)) if 1e-7<t<1-1e-7]
        if inflections:
            yield 'inflection_review','drawing_convention','info',{'pathTimes':inflections,
                'action':'Inflections may be intentional; review interpolation and use De-kink for HOI problems.'},'candidate',[start,end]
        stationary=[]
        for t in sorted(set(roots(3*A[0],2*B[0],C[0])+roots(3*A[1],2*B[1],C[1]))):
            speed=math.hypot(*(3*A[k]*t*t+2*B[k]*t+C[k] for k in range(2)))
            if 1e-7<t<1-1e-7 and speed<=1e-9*max(1.,*(math.hypot(*v) for v in (A,B,C))):stationary.append(t)
        if stationary:
            yield 'stationary_curve_review','suspicious','warning',{'pathTimes':stationary,
                'action':'Review a possible cusp or degenerate curve; no automatic smoothing.'},'suspicious',[start,end]
    if not state['closed']:
        yield 'open_fill_path','appearance','warning',{'action':'Confirm whether this is an intended open construction path or needs explicit closing.'},'candidate',[]


def layer_findings(states, *, upm=1000., width=0.):
    """Yield (path index, finding); nesting is reviewed only with clearance proof."""
    eligible=[]
    for index,state in states:
        if is_stroke(state) or not state['closed'] or len(state['nodes'])>512:continue
        try:area=signed_area(state)
        except (ValueError,RuntimeError,TypeError):continue
        eligible.append((index,state,area))
        if abs(area)<upm*upm*1e-6:
            yield index,('tiny_contour_review','suspicious','info',{'signedArea':area,
                'action':'Inspect intended dots/details and detached remove_overlap results before deleting debris.'},'candidate',[])
        points=state['nodes']
        if any(n['x'] < -4*upm or n['x'] > max(0.,width)+4*upm or abs(n['y'])>4*upm for n in points):
            yield index,('distant_contour_review','suspicious','info',{
                'distanceThresholdEm':4,'action':'Review possible off-canvas debris; wide or tall designs may be intentional.'},'candidate',[])
    if not eligible:return
    if sum(len(s['nodes']) for _,s,_ in eligible)>512:
        yield eligible[0][0],('layer_quality_held','unsupported','info',{'reason':'nesting audit is bounded to 512 total points'},'definite',[])
        return
    try:
        from .preparation.path_cleanup import topology
        nesting=topology([s for _,s,_ in eligible],.002)
    except ValueError as exc:
        yield eligible[0][0],('topology_review','suspicious','info',{'reason':str(exc),
            'action':'Review intersections, tangencies and intentional overlaps. Do not automatically remove source overlaps.'},'suspicious',[])
        return
    for (index,state,area),inside in zip(eligible,nesting):
        depth=sum(inside); ccw=depth%2==0
        if area and (area>0)!=ccw:
            yield index,('path_direction_review','suspicious','warning',{'nestingDepth':depth,'signedArea':area,
                'expectedDirection':'counterclockwise' if ccw else 'clockwise',
                'action':'Review correct_path_direction across explicit interpolation layers: it also changes starts and shape order. Recheck correspondence.'},'candidate',[])
