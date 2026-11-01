"""Closed Path Doctor cleanup settings; geometry stays in native preparation."""
from .outline import _object, _closed, _number
from .path_doctor import validate_options as scope_options
from .models import ProtocolError

CAPABILITY = 'path.cleanup.v1'
EXACT = ('duplicates', 'seams', 'collinear')
BOUNDED = ('near_nodes', 'align_handles', 'simplify_curves')
OPERATIONS = EXACT + BOUNDED


def validate_options(value):
    item = _object(value, 'path cleanup settings')
    _closed(item, {'glyphs', 'layers', 'policy', 'operations', 'maxDeviation', 'angleTolerance'}, 'path cleanup settings')
    scope = scope_options({'glyphs': item.get('glyphs'), 'layers': item.get('layers', 'all_interpolation_layers')})
    if scope['layers'] != 'all_interpolation_layers':
        raise ProtocolError('invalid_request', 'cleanup requires all_interpolation_layers to preserve correspondence')
    policy = item.get('policy', 'exact')
    if policy not in ('exact', 'bounded'):
        raise ProtocolError('invalid_request', 'cleanup policy must be exact or bounded')
    operations = item.get('operations', ['duplicates'])
    if (not isinstance(operations, list) or not operations or any(op not in OPERATIONS for op in operations)
            or len(set(operations)) != len(operations)):
        raise ProtocolError('invalid_request', 'select unique supported cleanup operations')
    if policy == 'exact' and any(op in BOUNDED for op in operations):
        raise ProtocolError('invalid_request', 'bounded operations require bounded policy')
    deviation = _number(item.get('maxDeviation', .5), 'maximum deviation')
    angle = _number(item.get('angleTolerance', 2.), 'angle tolerance')
    if not 0 < deviation <= 10 or not 0 < angle <= 10:
        raise ProtocolError('invalid_request', 'cleanup tolerances must be positive and at most 10')
    return {**scope, 'policy':policy, 'operations':[op for op in OPERATIONS if op in operations],
            'maxDeviation':deviation, 'angleTolerance':angle}
