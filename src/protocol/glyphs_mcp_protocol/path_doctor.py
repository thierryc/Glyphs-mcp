"""Closed Path Doctor diagnostic request and pure seam qualification."""
from __future__ import annotations

from .models import ProtocolError
from .outline import _object, _closed, _text, _hash

DIAGNOSTIC = 'path.diagnostics.v1'
REPAIR = 'outline.normalize-closed-seam.v1'


def validate_options(value):
    item = _object(value, 'path_diagnostics options')
    _closed(item, {'glyphs', 'layers'}, 'path_diagnostics options')
    names = item.get('glyphs')
    if names != 'all' and (not isinstance(names, list) or not 1 <= len(names) <= 10000
            or any(not isinstance(n, str) or not n for n in names) or len(set(names)) != len(names)):
        raise ProtocolError('invalid_request', 'diagnostic glyphs must be all or 1-10000 unique names')
    layers = item.get('layers', 'all_masters')
    if layers not in ('all_masters', 'all_interpolation_layers') and (not isinstance(layers, list) or not 1 <= len(layers) <= 100
            or any(not isinstance(n, str) or not n for n in layers) or len(set(layers)) != len(layers)):
        raise ProtocolError('invalid_request', 'diagnostic layers must be all_masters, all_interpolation_layers or exact IDs')
    return {'glyphs': names, 'layers': layers}


def operation(item):
    _closed(item, {'op', 'path', 'stateHash'}, 'normalize_closed_seam')
    from .outline import _index
    return {'op': 'normalize_closed_seam', 'path': _index(item.get('path'), 'seam path'),
            'stateHash': _hash(item.get('stateHash'), 'seam stateHash')}


def seam_pattern(path):
    nodes = path['nodes']
    return bool(path['closed'] and len(nodes) >= 3 and nodes[0]['type'] == 'line'
                and nodes[-1]['type'] in ('line', 'curve')
                and (nodes[0]['x'], nodes[0]['y']) == (nodes[-1]['x'], nodes[-1]['y']))


def qualify(path, *, referenced=False):
    """Only an automatic last→first zero line; no coincident-coordinate heuristic."""
    if not seam_pattern(path):
        return ['not the qualified redundant closed-seam pattern']
    reasons = []
    if path.get('locked'): reasons.append('path is locked')
    if referenced: reasons.append('native hint references this path; remapping is unsupported')
    nodes = path['nodes']; first, last = nodes[0], nodes[-1]
    if first.get('smooth', False) != last.get('smooth', False):
        reasons.append('seam connection flags conflict')
    if last.get('name') or any(n.get('attributeState', {}).get('userData') for n in nodes):
        reasons.append('node names/user data may contain authored references; resolve them explicitly')
    if path.get('attributeState', {}).get('userData'):
        reasons.append('path user data may contain unsupported references')
    for n in nodes:
        attrs = n.get('attributeState', {}).get('attributes', {})
        if any(k != 'penPoints' for k in attrs):
            reasons.append('unsupported node attributes/references'); break
    a = first.get('attributeState', {}).get('attributes', {}).get('penPoints', [])
    b = last.get('attributeState', {}).get('attributes', {}).get('penPoints', [])
    one = {'float': float(1).hex()}
    if a and (len(a) != 1 or not b or a[0] != b[-1]
              or a[0].get('penPoint', {}).get('t') != one):
        reasons.append('conflicting seam profiles: redundant control must exactly match incoming t=1, including inherited values')
    # Other on-curves/handles and native segment structure are checked independently.
    for node in nodes:
        for point in node.get('attributeState', {}).get('attributes', {}).get('penPoints', []):
            fields = point.get('penPoint', {})
            from .preparation.path_attributes import PEN_FIELDS, PEN_KEYS
            if set(fields) - set(PEN_FIELDS) - {'stored'} or set(fields.get('stored', {})) - PEN_KEYS:
                reasons.append('unsupported Pen-point fields')
            if fields.get('isLocked'):
                reasons.append('Pen point is locked')
    return sorted(set(reasons))


DUPLICATES = 'outline.remove-consecutive-duplicates.v1'


def duplicate_indices(state):
    """Interior adjacent zero LINE endpoints; never a curve or the closing seam."""
    nodes = state['nodes']
    return [i for i in range(1, len(nodes))
            if nodes[i]['type'] == 'line' and nodes[i-1]['type'] != 'offcurve'
            and (nodes[i]['x'], nodes[i]['y']) == (nodes[i-1]['x'], nodes[i-1]['y'])]


def qualify_duplicates(state, *, referenced=False):
    reasons = []
    indices = duplicate_indices(state)
    if not indices: reasons.append('no consecutive duplicate LINE endpoints')
    if state.get('locked'): reasons.append('path is locked')
    if referenced: reasons.append('native hint references this path')
    if state.get('attributeState', {}).get('userData'):
        reasons.append('path user data may contain authored references')
    for node in state['nodes']:
        attrs = node.get('attributeState', {})
        if attrs.get('userData') or node.get('name'):
            reasons.append('node metadata may contain authored references')
        if attrs.get('attributes'):
            reasons.append('node attributes or profiles require separate qualification')
    for i in indices:
        if state['nodes'][i].get('smooth', False) != state['nodes'][i-1].get('smooth', False):
            reasons.append('duplicate connection flags conflict')
    survivors = [n for i,n in enumerate(state['nodes']) if i not in indices]
    if sum(n['type'] != 'offcurve' for n in survivors) < 2:
        reasons.append('removal would leave a degenerate contour')
    return sorted(set(reasons))
