"""External spacing workflow: sampled evidence, reference policy, physical targets.

This is a port of the tested reference/area policy, without v1's integer rounding
or its broader spacing guards. It does not claim optimal optical spacing.
"""

import math
import unicodedata

FIGURES = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine')


def value(owner, name, default=None):
    result = getattr(owner, name, default)
    return result() if callable(result) else result


def bounds(layer):
    rect = layer.bounds
    return float(rect.origin.x), float(rect.origin.y), float(rect.size.width), float(rect.size.height)


def lookup(collection, key):
    try:
        return collection[key]
    except (KeyError, IndexError):
        return None


def exact_copy(layer):
    """Measure detached native geometry without Glyphs' display-path rounding."""
    copy = layer.copy()
    # Native component/corner resolution needs the font through its glyph.
    # This assigns context to the detached copy; it does not insert the layer.
    parent = getattr(layer, 'parent', None)
    if parent is not None:
        copy.parent = parent
    setter = getattr(copy, 'setTemporarilyDisableRounding_', None)
    if callable(setter):
        setter(True)
    refresh = getattr(copy, 'setNeedUpdateShapes', None)
    if callable(refresh):
        refresh()
    return copy


def glyph_class(glyph, layer):
    if float(layer.width) == 0:
        return 'zeroWidth'
    category = str(value(glyph, 'category', '') or '')
    subcategory = str(value(glyph, 'subCategory', '') or '').lower()
    name = str(glyph.name).split('.')[0]
    try:
        char = chr(int(value(glyph, 'unicode', '') or '', 16))
    except (ValueError, TypeError):
        char = name if len(name) == 1 else ''
    if category == 'Mark' or 'nonspacing' in subcategory or char and unicodedata.category(char).startswith('M'):
        return 'mark'
    if subcategory == 'uppercase' or char.isupper():
        return 'uppercase'
    if subcategory == 'lowercase' or char.islower():
        return 'lowercase'
    if char.isdecimal() or name in FIGURES:
        return 'decimalFigure'
    if category == 'Punctuation' or char and unicodedata.category(char).startswith('P'):
        return 'punctuation'
    return 'other'


def reference_layer(font, glyph, layer, requested):
    kind = glyph_class(glyph, layer)
    candidates = {'uppercase': ['H', 'x', '*'], 'lowercase': ['x', 'n', 'o', '*'],
                  'decimalFigure': ['one', 'zero', 'x', '*'], 'mark': ['*'],
                  'zeroWidth': ['*'], 'punctuation': ['*']}.get(kind, ['x', '*'])
    if requested != 'auto':
        candidates = [requested]
    master_id = str(layer.associatedMasterId or layer.layerId)
    for index, candidate in enumerate(candidates):
        ref = glyph if candidate == '*' else lookup(font.glyphs, candidate)
        ref_layer = layer if ref is glyph else lookup(ref.layers, master_id) if ref is not None else None
        if ref_layer is not None and ref is not glyph:
            ref_layer = exact_copy(ref_layer)
        if ref_layer is not None and bounds(ref_layer)[3] > 0:
            fallback = None if index == 0 else {'preferred': candidates[0], 'reason': 'preferred_reference_unavailable'}
            return ref_layer, {'requestedReference': requested, 'selectedReference': str(ref.name), 'fallback': fallback}
    raise ValueError('explicit reference is unavailable' if requested != 'auto' else 'no reference is available')


def preserved_width_reason(font, glyph, layer, mode):
    if mode == 'preserve':
        return 'explicit_width_preservation'
    if any(part in ('tf', 'tosf', 'tab', 'tabular') for part in str(glyph.name).split('.')[1:]):
        return 'tabular_glyph_name'
    params = value(font, 'customParameters', {})
    if bool(lookup(params, 'isFixedPitch') or value(font, 'isFixedPitch', False)):
        return 'font_fixed_pitch_metadata'
    if mode == 'proportional' or glyph_class(glyph, layer) != 'decimalFigure':
        return None
    widths = []
    for name in FIGURES:
        ref = lookup(font.glyphs, name)
        candidate = lookup(ref.layers, layer.associatedMasterId) if ref is not None else None
        if candidate is None:
            return None
        widths.append(float(candidate.width))
    if max(widths) - min(widths) <= float(font.upm) * 0.005:
        return 'default_figures_equal_width'
    return None


def sampled_edges(layer, ymin, ymax, step):
    x, bottom, w, height = bounds(layer)
    count = max(1, math.ceil((ymax - ymin) / step))
    if count > 4096:
        raise ValueError('spacing measurement exceeds 4096 samples')
    ys = [ymin + (ymax - ymin) * index / count for index in range(count + 1)]
    edges = []
    for y in ys:
        hits = list(layer.intersectionsBetweenPoints((x - 1, y), (x + w + 1, y), components=True) or [])
        # Glyphs 4 can omit one edge when the scan lies on a horizontal
        # contour boundary. Probe just inside that outer boundary; never
        # fill a genuinely empty interior height or a reference-only margin.
        if len(hits) < 4 and height > 0 and y in (bottom, bottom + height):
            inset = min(0.00001, height / 4)
            inside = y + inset if y == bottom else y - inset
            hits = list(layer.intersectionsBetweenPoints((x - 1, inside), (x + w + 1, inside), components=True) or [])
        edges.append((float(hits[1].x), float(hits[-2].x)) if len(hits) >= 4 else None)
    return ys, edges


def _area(ys, xs):
    return sum((ys[i+1] - ys[i]) * (xs[i] + xs[i+1]) / 2 for i in range(len(ys)-1))


def suggest(font, glyph, layer, options):
    kind = glyph_class(glyph, layer)
    row = {'glyph': str(glyph.name), 'layer': str(layer.layerId), 'glyphClass': kind}
    if kind in ('mark', 'zeroWidth'):
        return dict(row, status='preserved', reason='mark_or_zero_width', width=float(layer.width))
    if any(value(owner, key) for owner in (glyph, layer)
           for key in ('leftMetricsKey', 'rightMetricsKey', 'widthMetricsKey')):
        return dict(row, status='preserved', reason='metrics_keys')
    # Reading isAligned resolves native positioning. A mixed layer can be false
    # while a component has positive effectiveAlignment (aligned/horizontal).
    # Configured automaticAlignment alone does not prove positioning is active.
    if value(layer, 'isAligned', False) or any(
            value(c, 'effectiveAlignment', int(value(c, 'automaticAlignment', False))) > 0
            for c in layer.components):
        return dict(row, status='preserved', reason='native_component_alignment')
    x, y, w, h = bounds(layer)
    if w <= 0 or h <= 0:
        return dict(row, status='preserved', reason='no_measurable_outline')
    requested = options['references'].get(str(glyph.name), options['reference'])
    ref, provenance = reference_layer(font, glyph, layer, requested)
    row.update(provenance)
    _, ymin, _, height = bounds(ref)
    ymax = ymin + height
    if max(0, min(y+h, ymax)-max(y, ymin)) / height < 0.7:
        return dict(row, status='preserved', reason='insufficient_vertical_coverage')
    ys, edges = sampled_edges(layer, ymin, ymax, options['sampleStep'])
    valid = [edge for edge in edges if edge is not None]
    if not valid:
        return dict(row, status='preserved', reason='no_intersections_in_reference_zone')
    left, right = min(v[0] for v in valid), max(v[1] for v in valid)
    master = font.masters[str(layer.associatedMasterId)]
    xheight = float(value(master, 'xHeight', height) or height)
    depth = xheight * options['depth'] / 100
    ls = [min(v[0], left+depth) if v else left+depth for v in edges]
    rs = [max(v[1], right-depth) if v else right-depth for v in edges]
    # Retain the tested area policy's 45-degree reach limit at sampled heights.
    for indices in (range(len(ys)-1), range(len(ys)-2, -1, -1)):
        for i in indices:
            a, b = (i, i+1) if indices.step > 0 else (i+1, i)
            reach = abs(ys[b]-ys[a])
            ls[b], rs[b] = min(ls[b], ls[a]+reach), max(rs[b], rs[a]-reach)
    target = options['area'] * (float(font.upm)/1000)**2 * 100 / xheight
    lsb = target - _area(ys, [v-left for v in ls]) / height - (left-x)
    rsb = target - _area(ys, [right-v for v in rs]) / height - (x+w-right)
    reason = preserved_width_reason(font, glyph, layer, options['widthMode'])
    width = float(layer.width) if reason else w + lsb + rsb
    if reason:
        correction = (width - w - lsb - rsb) / 2
        lsb, rsb = lsb+correction, rsb+correction
    return dict(row, status='suggested', before={'width': float(layer.width), 'lsb': x, 'rsb': float(layer.width)-x-w},
                after={'width': width, 'lsb': lsb, 'rsb': rsb}, dx=lsb-x, preservedWidthReason=reason,
                measurement={'yMin': ymin, 'yMax': ymax, 'samples': len(ys)})


def validate_options(raw):
    options = {'reference': 'auto', 'references': {}, 'widthMode': 'auto', 'area': 400.0, 'depth': 15.0,
               'sampleStep': 5.0, 'masters': []}
    if not isinstance(raw, dict) or set(raw)-options.keys():
        raise ValueError('unsupported spacing options')
    options.update(raw)
    if options['widthMode'] not in ('auto', 'preserve', 'proportional'):
        raise ValueError('widthMode must be auto, preserve or proportional')
    refs = options['references']
    if not isinstance(refs, dict) or len(refs)>10000 or any(not isinstance(k,str) or not k for k in refs):
        raise ValueError('references must map glyph names to reference names')
    if any(not isinstance(v,str) or not v.strip() or len(v)>255 for v in [options['reference'], *refs.values()]):
        raise ValueError('reference names must be nonempty strings')
    for key, low, high in (('area', 0, 10000), ('depth', 0, 100), ('sampleStep', 0.5, 100)):
        v = options[key]
        if isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(key+' is outside the supported measurement range')
    if not isinstance(options['masters'],list) or len(options['masters'])>100 or any(not isinstance(v,str) or not v for v in options['masters']):
        raise ValueError('masters must be a bounded list of master IDs')
    return options
