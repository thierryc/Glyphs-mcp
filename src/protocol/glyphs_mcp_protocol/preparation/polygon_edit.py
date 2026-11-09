"""Shared guarded materialization for detached fitting and typed native apply."""
from copy import deepcopy
from ..outline import path_hash
from ..polygon_fitting import validate_polygon, sub, unit, dot
from .path_doctor import path_state, referenced
from .path_cleanup import protected, stroked, validate_bounded
from .outline import _value, _set_nodes


def project(state, operation):
    points = validate_polygon(state)
    if path_hash(state) != operation['stateHash']:
        raise ValueError('polygon fitting state guard is stale')
    if protected(state) or stroked(state):
        raise ValueError('polygon fitting holds locks, strokes, profiles and authored node/path references')
    segments = operation['segments']; count = len(points)
    starts = [s['startNode'] for s in segments]
    if (starts[0] != 0 or starts != sorted(set(starts)) or starts[-1] >= count
            or [s['endNode'] for s in segments] != starts[1:]+[0]):
        raise ValueError('fitted segments must retain node 0 and follow the source contour order')
    corners = set(operation['cornerNodes'])
    if not corners <= set(starts):
        raise ValueError('fitting removed a protected corner')
    nodes, sources = [], []
    for i,segment in enumerate(segments):
        index = segment['startNode']; node = deepcopy(state['nodes'][index])
        previous = segments[i-1]
        node['type'] = 'curve' if previous['controls'] else 'line'
        a = previous['controls'][-1] if previous['controls'] else state['nodes'][previous['startNode']]
        b = segment['controls'][0] if segment['controls'] else state['nodes'][segment['endNode']]
        incoming = sub(points[index],(a['x'],a['y']))
        outgoing = sub((b['x'],b['y']),points[index])
        node['smooth'] = index not in corners and dot(unit(incoming),unit(outgoing)) >= 1-1e-12
        nodes.append(node);sources.append(index)
        for control in segment['controls']:
            nodes.append({**control, 'type':'offcurve', 'smooth':False, 'name':None,
                          'attributeState':{'attributes':{}, 'userData':{}}})
            sources.append(None)
    if len(nodes) >= count:
        raise ValueError('polygon fitting must reduce total stored points')
    return {**state, 'nodes':nodes}, sources


def apply(layer, path, operation):
    before = path_state(path)
    expected, sources = project(before, operation)
    if (_value(layer,'locked',False) or _value(_value(layer,'parent',None),'locked',False)
            or referenced(layer,path)):
        raise ValueError('polygon fitting holds locked or hinted targets')
    # Certify all contours, so a fitted curve cannot cross another contour.
    original = [path_state(p) for p in layer.paths]
    index = list(layer.paths).index(path)
    trial = list(original); trial[index] = expected
    validate_bounded(original, trial, operation['maxDeviation'])
    from GlyphsApp import GSNode
    old = list(path.nodes); nodes = []
    for state, source in zip(expected['nodes'],sources):
        node = old[source] if source is not None else GSNode()
        if source is None:
            node.position = (state['x'],state['y'])
        node.type = state['type']; node.smooth = state['smooth']
        nodes.append(node)
    _set_nodes(path,nodes)
    actual = path_state(path)
    if actual != expected:
        raise ValueError('native fitting changed prepared coordinates or node/path attributes')
    return {'retainedNodeMap':{str(source):i for i,source in enumerate(sources) if source is not None},
            'beforeNodes':len(old),'afterNodes':len(nodes)}
