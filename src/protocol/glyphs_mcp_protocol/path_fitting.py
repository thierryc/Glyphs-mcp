"""Explicit polygon reconstruction; ordinary cleanup never enables this mode."""
from .outline import _object, _closed, _number, _index
from .models import ProtocolError

CAPABILITY = 'path.fit-curves.v1'
WRITE_CAPABILITY = 'outline.fit-polygon.v1'
MAX_INPUT_NODES = 512
MAX_SEGMENTS = 256


def indices(value, label):
    if not isinstance(value, list) or len(value) > MAX_INPUT_NODES:
        raise ProtocolError('invalid_request', label + ' must be a list of at most 512 indices')
    result = [_index(n, label) for n in value]
    if len(result) != len(set(result)):
        raise ProtocolError('invalid_request', label + ' must contain unique indices')
    return sorted(result)


def validate_options(value):
    item = _object(value, 'path fitting settings')
    _closed(item, {'targets', 'layers', 'maxDeviation', 'cornerAngle'}, 'path fitting settings')
    if item.get('layers', 'all_interpolation_layers') != 'all_interpolation_layers':
        raise ProtocolError('invalid_request', 'fitting requires all_interpolation_layers')
    deviation = _number(item.get('maxDeviation', .5), 'maximum deviation')
    angle = _number(item.get('cornerAngle', 45), 'protected corner angle')
    if not 0 < deviation <= 10 or not 0 < angle <= 180:
        raise ProtocolError('invalid_request', 'deviation must be in (0,10] and corner angle in (0,180]')
    targets = item.get('targets')
    if not isinstance(targets, list) or not 1 <= len(targets) <= 100:
        raise ProtocolError('invalid_request', 'fitting requires 1-100 explicit glyph targets')
    result, names = [], set()
    for raw in targets:
        target = _object(raw, 'fitting target')
        _closed(target, {'glyph', 'paths'}, 'fitting target')
        name, paths = target.get('glyph'), target.get('paths')
        if not isinstance(name, str) or not name.strip() or name != name.strip() or name in names:
            raise ProtocolError('invalid_request', 'fitting glyph names must be nonempty and unique')
        if not isinstance(paths, list) or not 1 <= len(paths) <= 100:
            raise ProtocolError('invalid_request', 'select 1-100 explicit paths per glyph')
        names.add(name)
        selected, seen = [], set()
        for raw_path in paths:
            path = _object(raw_path, 'fitting path')
            _closed(path, {'path', 'keepNodes', 'cornerNodes'}, 'fitting path')
            index = _index(path.get('path'), 'fitting path')
            if index in seen:
                raise ProtocolError('invalid_request', 'fitting path indices must be unique')
            seen.add(index)
            selected.append({'path': index, 'keepNodes': indices(path.get('keepNodes', []), 'retained nodes'),
                             'cornerNodes': indices(path.get('cornerNodes', []), 'corner nodes')})
        result.append({'glyph': name, 'paths': sorted(selected, key=lambda p: p['path'])})
    return {'targets': result, 'layers': 'all_interpolation_layers',
            'maxDeviation': deviation, 'cornerAngle': angle}
