"""Mirror paths vertically. Parameters: pivot and optional pivotY.

pivot: layer_bounds_center (default), path_bounds_center, baseline, custom.
The wrapper supplies the selected foreground or background layer.
"""
def run(layer, params, context):
    paths = list(layer.paths)
    if not paths:
        return
    pivot = params.get('pivot', 'layer_bounds_center')
    if pivot not in ('layer_bounds_center', 'path_bounds_center', 'baseline', 'custom'):
        raise ValueError('unsupported vertical-flip pivot')
    def center(items):
        return (min(p.bounds.origin.y for p in items) +
                max(p.bounds.origin.y + p.bounds.size.height for p in items)) / 2
    fixed = float(params['pivotY']) if pivot == 'custom' else 0 if pivot == 'baseline' else center(paths)
    for path in paths:
        y = center([path]) if pivot == 'path_bounds_center' else fixed
        for node in path.nodes:
            node.position = (node.position.x, 2 * y - node.position.y)
