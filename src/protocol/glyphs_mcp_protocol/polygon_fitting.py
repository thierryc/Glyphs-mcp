"""Dependency-free family fitting with conservative, continuous span bounds.

Chord-length parameters associate each source LINE with a cubic subinterval.
The norm of the Bernstein difference control hull bounds every paired point,
and consequently both directed boundary distances. No point-sampling claim is
used to accept a fit. Native rounding and whole-layer topology are checked by
the caller after materializing the proposal on detached layers.
"""
import math
from .path_fitting import MAX_INPUT_NODES, MAX_SEGMENTS


def add(a, b): return (a[0] + b[0], a[1] + b[1])
def sub(a, b): return (a[0] - b[0], a[1] - b[1])
def mul(a, t): return (a[0] * t, a[1] * t)
def dot(a, b): return a[0] * b[0] + a[1] * b[1]
def unit(a):
    length = math.hypot(*a)
    if length <= 1e-12: raise ValueError('zero or unresolved polygon edge/tangent')
    return mul(a, 1 / length)


def split(curve, t=.5):
    a, b, c, d = curve
    ab, bc, cd = [add(mul(p, 1-t), mul(q, t)) for p, q in ((a,b), (b,c), (c,d))]
    abc, bcd = add(mul(ab, 1-t), mul(bc, t)), add(mul(bc, 1-t), mul(cd, t))
    middle = add(mul(abc, 1-t), mul(bcd, t))
    return (a, ab, abc, middle), (middle, bcd, cd, d)


def interval(curve, low, high):
    left = split(curve, high)[0] if high < 1 else curve
    return split(left, low / high)[1] if low else left


def difference_bound(controls, tolerance, depth=0):
    bound = max(math.hypot(*p) for p in controls)
    if bound <= tolerance or depth >= 10: return bound
    left, right = split(controls)
    # A failing lower bound cannot be improved by further subdivision.
    if math.hypot(*left[-1]) > tolerance: return bound
    return max(difference_bound(left, tolerance, depth+1), difference_bound(right, tolerance, depth+1))


def span_bound(points, times, curve, tolerance):
    maximum, worst = 0., 1
    for i, (a,b) in enumerate(zip(points, points[1:])):
        controls = interval(curve, times[i], times[i+1])
        line = (a, add(mul(a, 2/3), mul(b, 1/3)), add(mul(a, 1/3), mul(b, 2/3)), b)
        error = difference_bound(tuple(sub(p,q) for p,q in zip(controls,line)), tolerance)
        if error > maximum:
            maximum, worst = error, min(max(1, i+1), len(points)-2)
    return maximum, worst


def parameters(points):
    lengths = [0.]
    for a,b in zip(points, points[1:]): lengths.append(lengths[-1] + math.dist(a,b))
    if any(b-a <= 1e-12 for a,b in zip(lengths,lengths[1:])):
        raise ValueError('duplicate polygon endpoints require separate exact cleanup')
    return [v / lengths[-1] for v in lengths]


def cubic(points, times, outgoing, incoming):
    """Least-squares positive handle lengths, with fixed endpoints/tangents."""
    a, d = points[0], points[-1]
    aa = ab = bb = ar = br = 0.
    for point,t in zip(points[1:-1],times[1:-1]):
        u = 1-t; b0,b1,b2,b3 = u**3,3*u*u*t,3*u*t*t,t**3
        left,right = mul(outgoing,b1),mul(incoming,-b2)
        residual = sub(point,add(mul(a,b0+b1),mul(d,b2+b3)))
        aa += dot(left,left); ab += dot(left,right); bb += dot(right,right)
        ar += dot(left,residual); br += dot(right,residual)
    det = aa*bb-ab*ab
    if abs(det) <= 1e-14 * max(1.,aa*bb):
        alpha = beta = math.dist(a,d)/3
    else:
        alpha,beta = (ar*bb-br*ab)/det,(br*aa-ar*ab)/det
    if min(alpha,beta) <= 1e-10 or not all(math.isfinite(v) for v in (alpha,beta)):
        alpha = beta = math.dist(a,d)/3
    return a,add(a,mul(outgoing,alpha)),sub(d,mul(incoming,beta)),d


def validate_polygon(state):
    nodes = state['nodes']
    if not state['closed'] or not 4 <= len(nodes) <= MAX_INPUT_NODES:
        raise ValueError('fitting requires a closed polygon with 4-512 nodes')
    if any(n['type'] != 'line' for n in nodes):
        raise ValueError('fitting accepts LINE polygons only; existing curves use coordinated cleanup')
    if not all(math.isfinite(n[k]) for n in nodes for k in ('x','y')):
        raise ValueError('non-finite polygon coordinates')
    points = [(n['x'],n['y']) for n in nodes]
    parameters(points+[points[0]])
    return points


def fit_family_iter(states, *, keep_nodes=(), corner_nodes=(), corner_angle=45., max_deviation=.5):
    """Yield between family spans; return one corresponding segment plan per layer."""
    families = [validate_polygon(s) for s in states]
    if not families or len({len(p) for p in families}) != 1:
        raise ValueError('polygon family requires corresponding node counts')
    count = len(families[0]); corners = set(corner_nodes); keep = {0, *keep_nodes, *corners}
    if any(type(i) is not int or not 0 <= i < count for i in keep):
        raise ValueError('retained/corner node is unavailable')
    for points in families:
        for i in range(count):
            a,b = unit(sub(points[i],points[i-1])),unit(sub(points[(i+1)%count],points[i]))
            angle = math.degrees(math.acos(max(-1.,min(1.,dot(a,b)))))
            if angle >= corner_angle: corners.add(i)
    keep.update(corners)
    # A closed curve needs distinct endpoints for each fitting span.
    if len(keep) < 2: keep.add(count//2)
    knots = sorted(keep)
    pending = [(a,b) for a,b in zip(knots,knots[1:]+[count])]
    accepted = []
    def tangent(points, index, forward):
        i=index%count
        if i in corners:
            return unit(sub(points[(i+1)%count],points[i])) if forward else unit(sub(points[i],points[i-1]))
        incoming = unit(sub(points[i],points[i-1]));outgoing=unit(sub(points[(i+1)%count],points[i]))
        return unit(add(incoming,outgoing))
    while pending:
        start,end = pending.pop(0)
        plans=[];worst_error=-1.;worst_node=None
        def straight(points):
            section=[points[i%count] for i in range(start,end+1)]
            chord=sub(section[-1],section[0]);length=math.hypot(*chord)
            if length<=1e-12:return False
            previous=-1.
            for point in section:
                delta=sub(point,section[0]);projection=dot(delta,chord)/(length*length)
                if abs(chord[0]*delta[1]-chord[1]*delta[0])>1e-10*length or projection<previous:return False
                previous=projection
            direction=unit(chord)
            # A short source edge is not necessarily an intentional straight
            # section. Retaining it at a smooth curve join would leave a kink.
            return (dot(direction,tangent(points,start,True))>=1-1e-12
                    and dot(direction,tangent(points,end,False))>=1-1e-12)
        all_linear=all(straight(points) for points in families)
        for points in families:
            section=[points[i%count] for i in range(start,end+1)]
            if all_linear:
                plans.append(([],0.));continue
            times=parameters(section)
            curve=cubic(section,times,tangent(points,start,True),tangent(points,end,False))
            error,offset=span_bound(section,times,curve,max_deviation*.75)
            plans.append(([{'x':p[0],'y':p[1]} for p in curve[1:3]],error))
            if error>worst_error:worst_error,worst_node=error,start+offset
        if worst_error>max_deviation*.75:
            if worst_node is None or not start<worst_node<end:
                raise ValueError('fitting could not resolve its deviation bound')
            pending[0:0]=[(start,worst_node),(worst_node,end)]
        else:
            accepted.append((start,end,plans))
        if len(pending)+len(accepted)>MAX_SEGMENTS:
            raise ValueError('fitting exceeds the 256-segment limit')
        yield
    accepted.sort(key=lambda item:item[0])
    result=[]
    for layer in range(len(families)):
        segments=[{'startNode':a,'endNode':b%count,'controls':plans[layer][0]} for a,b,plans in accepted]
        total=len(segments)+sum(len(s['controls']) for s in segments)
        if total>=count:
            raise ValueError('no point reduction within the deviation budget; retain the polygon or review tolerance')
        result.append({'segments':segments,'cornerNodes':sorted(corners),
                       'continuousSpanBound':max(p[layer][1] for _,_,p in accepted),
                       'beforeNodes':count,'afterNodes':total})
    return result
