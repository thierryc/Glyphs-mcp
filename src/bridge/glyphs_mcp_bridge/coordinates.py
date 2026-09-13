"""Explicit native coordinate setters; workflow decisions remain external."""

from glyphs_mcp_protocol.coordinates import topology_hash


def signature(layer):
    return topology_hash([[bool(p.closed),[str(n.type) for n in p.nodes]] for p in layer.paths],
                         [str(a.name) for a in layer.anchors],
                         [[str(c.componentName),bool(c.automaticAlignment)] for c in layer.components])


def targets(layer,change):
    if signature(layer)!=change['topologyHash']:
        raise ValueError('coordinate target topology or component alignment changed')
    paths=list(layer.paths);components=list(layer.components)
    return ([(list(paths[p].nodes)[n],'position') for p,n in change['nodes']]+
            [(layer.anchors[name],'position') for name in change['anchors']]+
            [(components[i],'transform') for i in change['components']])


def read(layer,change):
    return [list(getattr(owner,field)) for owner,field in targets(layer,change)]


def write(layer,change,*,reverse=False):
    selected=targets(layer,change)
    before=[tuple(getattr(owner,field)) for owner,field in selected]
    wanted=change['before'] if reverse else change['after']
    # Some native scaled/skewed matrices cannot be restored by the matrix
    # setter. Prove both directions on copies before any live coordinate write.
    for (owner,field),original,value in zip(selected,before,wanted):
        if field=='transform':
            clone=owner.copy()
            for matrix in (original,tuple(value)):
                clone.transform=matrix
                if tuple(clone.transform)!=matrix:
                    raise ValueError('native component matrix cannot be applied and restored exactly')
    for (owner,field),value in zip(selected,wanted):
        setattr(owner,field,tuple(value))


def geometry_targets(layer):
    # Translation affects foreground positions, not component linear matrices
    # or layer decorations such as background images and guides.
    return ([(n, 'position') for p in layer.paths for n in p.nodes] +
            [(a, 'position') for a in layer.anchors] + [(c, 'position') for c in layer.components])


def read_state(layer, change):
    kind = change['kind']
    if kind == 'set':
        value = getattr(layer, change['field'])
        return value() if callable(value) else value
    if kind == 'coordinates':
        return read(layer, change)
    if kind == 'start_node':
        return tuple(layer.paths[change['path']].nodes)
    values = []
    for owner, field in geometry_targets(layer):
        value = getattr(owner, field)
        values.append(tuple(value) if not hasattr(value, 'x') else (value.x, value.y))
    return values


def write_state(layer, change, value):
    kind = change['kind']
    if kind == 'set':
        setattr(layer, change['field'], value)
    elif kind == 'coordinates':
        write(layer, dict(change, after=value))
    elif kind == 'start_node':
        layer.paths[change['path']].makeNodeFirst_(value[-1])
    else:
        for (owner, field), item in zip(geometry_targets(layer), value):
            setattr(owner, field, item)
