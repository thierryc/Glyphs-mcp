# MenuTitle: Derive Small and Petite Caps
# encoding: utf-8
"""Explicit, save-free construction. Run through a native whole-script job.

See references/helper.md for the closed request and handoff format. Importing
this file does not import GlyphsApp or perform font/file operations.
"""
import hashlib
import json
import math
from contextlib import contextmanager
from pathlib import Path

SCHEMA = 1
KINDS = {'sc', 'pc'}


def value(obj, key, default=None):
    result = getattr(obj, key, default)
    return result() if callable(result) else result


def number(item, label, positive=False):
    if isinstance(item, bool) or not isinstance(item, (float, int)) or not math.isfinite(item):
        raise ValueError(label + ' must be finite')
    if positive and item <= 0:
        raise ValueError(label + ' must be positive')
    return float(item)


def digest(item):
    return 'sha256:' + hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def point(item):
    return [float(item.x), float(item.y)]


def layer_state(layer):
    shapes = []
    for shape in layer.shapes:
        if hasattr(shape, 'nodes'):
            shapes.append(dict(nodes=[dict(position=point(n.position), type=str(n.type),
                smooth=bool(n.smooth), name=n.name) for n in shape.nodes], closed=bool(shape.closed)))
        else:
            shapes.append(dict(component=str(shape.componentName), transform=list(shape.transform),
                               automaticAlignment=bool(shape.automaticAlignment)))
    return dict(shapes=shapes, anchors=[dict(name=a.name, position=point(a.position)) for a in layer.anchors],
        width=float(layer.width), hints=len(layer.hints),
        keys=[getattr(layer, key, None) for key in ('leftMetricsKey', 'rightMetricsKey', 'widthMetricsKey')])


def topology(layer):
    return [(('path', bool(s.closed), tuple(str(n.type) for n in s.nodes)) if hasattr(s, 'nodes')
             else ('component', str(s.componentName))) for s in layer.shapes]


def smart_component(component):
    # Glyphs 4's empty proxy can have values() == None and a failing __len__.
    for owner, key in ((component, 'smartComponentValues'),
                       (getattr(component, 'component', None), 'axes')):
        collection = value(owner, key)
        if collection is None:
            continue
        values = getattr(collection, 'values', None)
        collection = values() if callable(values) else collection
        if collection is not None and list(collection):
            return True
    return False


def glyph_state(glyph, masters):
    if glyph is None:
        return None
    return dict(name=glyph.name, unicodes=list(glyph.unicodes or []),
        keys=[getattr(glyph, k, None) for k in ('leftMetricsKey', 'rightMetricsKey', 'widthMetricsKey')],
        layers={m: layer_state(glyph.layers[m]) if glyph.layers[m] is not None else None for m in masters})


def target_name(source, kind, api):
    """Resolve through character metadata, preserving nontrivial nice names."""
    if kind not in KINDS:
        raise ValueError('kind must be sc or pc')
    info = api.glyphInfoForName(source)
    text = value(info, 'unicharString') if info is not None else None
    # Unicode lowercase of dotted capital I is a two-codepoint sequence.
    exceptions = {'Idotaccent': 'idotaccent', 'Germandbls': 'germandbls'}
    lower_name = exceptions.get(source)
    if lower_name is None and text and len(text.lower()) == 1:
        mapped = api.glyphInfoForUnicode('%04X' % ord(text.lower()))
        lower_name = value(mapped, 'name') if mapped is not None else None
    if not lower_name or '.' in source:
        raise ValueError('Supply an explicit reviewed destination for ' + source)
    return lower_name + '.' + kind


def _identity(font, masters):
    return dict(familyName=str(font.familyName), unitsPerEm=int(font.upm),
        masters={m: dict(capHeight=float(font.masters[m].capHeight),
                        xHeight=float(font.masters[m].xHeight)) for m in masters})


def _request(font, params, api):
    if not isinstance(params, dict) or set(params) - {'stage', 'masters', 'rows', 'sets', 'expected',
            'identity', 'componentMap', 'offsetQualification', 'reportPath', 'review'}:
        raise ValueError('Unknown request fields')
    stage = params.get('stage')
    if stage not in {'inspect', 'construct', 'verify'}:
        raise ValueError('stage must be inspect, construct or verify')
    masters = params.get('masters')
    if not isinstance(masters, list) or not masters or len(set(masters)) != len(masters):
        raise ValueError('Supply unique exact ordinary master IDs')
    known = {str(m.id) for m in font.masters}
    if any(not isinstance(m, str) or m not in known for m in masters):
        raise ValueError('Missing or invalid master')
    rows = params.get('rows')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Supply explicit source rows')
    resolved, destinations = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'source', 'destination', 'kind'}:
            raise ValueError('Invalid glyph row')
        source, kind = row.get('source'), row.get('kind')
        if not isinstance(source, str) or kind not in KINDS or font.glyphs[source] is None:
            raise ValueError('Missing source or invalid cap kind')
        dest = row.get('destination') or target_name(source, kind, api)
        if (not isinstance(dest, str) or not dest.endswith('.' + kind) or dest.startswith('.') or dest == source or
                any(c.isspace() or ord(c) < 32 for c in dest) or dest in destinations):
            raise ValueError('Invalid or duplicate destination: ' + str(dest))
        destinations.add(dest)
        resolved.append(dict(source=source, destination=dest, kind=kind))
    if destinations & {r['source'] for r in resolved}:
        raise ValueError('A destination must not also be a source')
    return stage, masters, resolved


def _dependencies(font, rows, masters, component_map):
    names = {r['source'] for r in rows} | {r['destination'] for r in rows}
    names.update(v for mapping in component_map.values() for v in mapping.values())
    pending = list(names)
    while pending:
        name = pending.pop()
        glyph = font.glyphs[name]
        if glyph is None:
            continue
        for mid in masters:
            layer = glyph.layers[mid]
            if layer is None:
                raise ValueError('Missing source/dependency master layer: ' + name + '/' + mid)
            for component in layer.components:
                dep = component.componentName
                if font.glyphs[dep] is None:
                    raise ValueError('Missing component dependency: ' + dep)
                if dep not in names:
                    names.add(dep); pending.append(dep)
    return sorted(names)


@contextmanager
def precision(layer):
    setter = getattr(layer, 'setTemporarilyDisableRounding_', None)
    getter = getattr(layer, 'temporarilyDisableRounding', None)
    if not callable(setter) or getter is None:
        raise ValueError('Native precision API unavailable')
    previous = bool(getter() if callable(getter) else getter)
    setter(True)
    try:
        yield
    finally:
        setter(previous)


def _settings(params, kind, mid):
    settings = params.get('sets', {}).get(kind, {}).get(mid)
    if not isinstance(settings, dict) or set(settings) != {'height', 'scaleX', 'offsetX', 'offsetY', 'tracking'}:
        raise ValueError('Each kind/master needs height, scaleX, offsetX, offsetY and tracking')
    return {k: number(v, k, k in {'height', 'scaleX'}) for k, v in settings.items()}


def _offset_filter(params, api):
    """Only the layer-local built-in adapter qualified in this skill is allowed."""
    qualification = params.get('offsetQualification') or {}
    if qualification.get('build') != str(api.buildNumber) or qualification.get('adapter') != 'layer-filter-keep':
        raise ValueError('Offset needs a successful disposable qualification for this exact Glyphs build')
    for item in api.filters:
        if type(item).__name__ == 'GlyphsFilterOffsetCurve' and callable(getattr(item, 'filter', None)):
            return item
    raise ValueError('Qualified layer-local Offset Curve API unavailable; use the documented UI handoff')


def _clear_keys(owner):
    for key in ('leftMetricsKey', 'rightMetricsKey', 'widthMetricsKey'):
        setattr(owner, key, None)


def _base_layer(source, master, settings, params, api):
    cap = number(master.capHeight, 'source cap height', True)
    sy = (settings['height'] - 2 * settings['offsetY']) / cap
    if sy <= 0:
        raise ValueError('Offset exceeds target height')
    layer = source.copy()
    _clear_keys(layer)
    layer.hints = []
    # Backgrounds, guides and annotations are not generated foreground material.
    layer.background = None
    layer.guides = []
    layer.annotations = []
    with precision(layer):
        layer.applyTransform((settings['scaleX'], 0, 0, sy, settings['offsetX'], settings['offsetY']))
        if settings['offsetX'] or settings['offsetY']:
            before = topology(layer)
            adapter = _offset_filter(params, api)
            adapter.filter(layer, False, {0: settings['offsetX'], 1: settings['offsetY'],
                                         2: 0, 3: 0.5, 4: 'keep'})
            if topology(layer) != before:
                raise ValueError('Offset changed topology despite Keep Compatible')
        # Tracking adds space on both sides. Width is explicit, never synced to uppercase.
        layer.applyTransform((1, 0, 0, 1, settings['tracking'], 0))
        layer.width = float(source.width) * settings['scaleX'] + 2 * (settings['offsetX'] + settings['tracking'])
    return layer


def measurements(layer, height):
    bounds = layer.bounds
    return dict(width=float(layer.width), bounds=[float(bounds.origin.x), float(bounds.origin.y),
        float(bounds.size.width), float(bounds.size.height)],
        topOvershoot=float(bounds.origin.y + bounds.size.height) - height,
        bottomOvershoot=-float(bounds.origin.y), topology=topology(layer),
        anchors=[dict(name=a.name, position=point(a.position)) for a in layer.anchors])


def run_caps(font, params, api=None):
    if api is None:
        from GlyphsApp import Glyphs
        api = Glyphs
    stage, masters, rows = _request(font, params, api)
    identity = _identity(font, masters)
    if stage != 'inspect' and params.get('identity') != identity:
        raise ValueError('Font binding or metrics changed; inspect the exact font again')
    component_map = params.get('componentMap', {})
    if (not isinstance(component_map, dict) or set(component_map) - KINDS or
            any(not isinstance(mapping, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                for k, v in mapping.items()) for mapping in component_map.values())):
        raise ValueError('componentMap must map each cap kind to explicit source/destination names')
    dependencies = _dependencies(font, rows, masters, component_map)
    guards = {n: digest(glyph_state(font.glyphs[n], masters)) for n in dependencies}
    if stage == 'construct' and params.get('expected') != guards:
        raise ValueError('Source, destination or dependency changed; inspect again before construction')
    report = dict(schemaVersion=SCHEMA, stage=stage, identity=identity, masters=masters, rows=rows,
        guards=guards, targets=[], created=[], preserved=[], skipped=[], needsReview=[],
        parameters=params.get('sets', {}), review=params.get('review', {}), changesVerified=False, interpolationVerified=False,
        featureBehaviorVerified=False)
    report_path = params.get('reportPath')
    if report_path is not None and (not Path(report_path).is_absolute() or Path(report_path).exists()
                                   or not Path(report_path).parent.is_dir()):
        raise ValueError('reportPath must be a new absolute file in an existing task directory')
    planned = []
    row_map = {(r['source'], r['kind']): r['destination'] for r in rows}
    # Build every detached outline and validate every dependency before font writes.
    for row in rows:
        source, dest, kind = row['source'], row['destination'], row['kind']
        glyph = font.glyphs[source]
        existing = font.glyphs[dest]
        item = dict(row, status='inspected', measurements={})
        report['targets'].append(item)
        if existing is not None:
            report['preserved'].append(dest); item['status'] = 'preserved'
        layers = [glyph.layers[m] for m in masters]
        reason = None
        if any(l is None for l in layers):
            reason = 'missing ordinary master layer'
        elif any(l.paths and l.components for l in layers):
            reason = 'mixed paths and components require designer construction'
        elif any(not l.shapes or any(hasattr(s, 'closed') and not s.closed for s in l.shapes) for l in layers):
            reason = 'empty or open foreground requires designer construction'
        elif any(topology(l) != topology(layers[0]) for l in layers[1:]):
            reason = 'source masters are incompatible'
        elif any(smart_component(c) for l in layers for c in l.components):
            reason = 'smart components require explicit designer construction'
        if reason:
            item.update(status='needs_review', reason=reason)
            report['skipped'].append(dest); report['needsReview'].append(dict(glyph=dest, reason=reason))
            continue
        if stage == 'construct' and existing is None:
            from GlyphsApp import GSGlyph
            new = GSGlyph(dest); new.unicodes = []; _clear_keys(new)
            for mid, source_layer in zip(masters, layers):
                settings = _settings(params, kind, mid)
                if source_layer.components:
                    layer = source_layer.copy(); _clear_keys(layer); layer.hints = []; layer.background = None
                    layer.guides = []; layer.annotations = []
                    for component in layer.components:
                        old = component.componentName
                        mapped = component_map.get(kind, {}).get(old) or row_map.get((old, kind))
                        if not mapped or (font.glyphs[mapped] is None and mapped not in row_map.values()):
                            raise ValueError('Review a derived component mapping for ' + old)
                        if not component.automaticAlignment:
                            raise ValueError('Manual component placement needs designer review: ' + source)
                        component.componentName = mapped
                    # Anchors are rebuilt by native composition; never retain uppercase anchors.
                    layer.anchors = []
                else:
                    layer = _base_layer(source_layer, font.masters[mid], settings, params, api)
                layer.layerId = mid; layer.associatedMasterId = mid
                new.layers[mid] = layer
            planned.append((row, new))
    # Order new composite dependencies before their owners; cycles fail before attachment.
    ordered, ready = [], {g.name for g in font.glyphs}
    pending = list(planned)
    while pending:
        eligible = [(r, g) for r, g in pending if all(c.componentName in ready
                    for mid in masters for c in g.layers[mid].components)]
        if not eligible:
            raise ValueError('Unresolved or cyclic derived component dependencies')
        for pair in eligible:
            pending.remove(pair); ordered.append(pair); ready.add(pair[1].name)
    if ordered:
        enabled = bool(font.isUpdateInterfaceEnabled())
        if enabled: font.disableUpdateInterface()
        try:
            for row, glyph in ordered:
                font.glyphs.append(glyph)
                report['created'].append(glyph.name)
            for row, glyph in ordered:
                for mid in masters:
                    layer = glyph.layers[mid]
                    if layer.components:
                        layer.doAlignComponents()
                        layer.addMissingAnchors()
        finally:
            if enabled: font.enableUpdateInterface()
    for item in report['targets']:
        dest, kind = item['destination'], item['kind']
        glyph = font.glyphs[dest]
        if glyph is None:
            continue
        if dest in report['created']: item['status'] = 'created'
        item['constructionMethod'] = ('components' if glyph.layers[masters[0]].components else
            'offset' if any(params.get('sets', {}).get(kind, {}).get(m, {}).get(k, 0)
                            for m in masters for k in ('offsetX', 'offsetY')) else 'scale_only')
        for mid in masters:
            settings = params.get('sets', {}).get(kind, {}).get(mid, {})
            if glyph.layers[mid] is not None:
                item['measurements'][mid] = measurements(glyph.layers[mid], settings.get('height', 0))
        structures = [topology(glyph.layers[mid]) for mid in masters if glyph.layers[mid] is not None]
        item['mastersCompatible'] = (len(structures) == len(masters) and all(s == structures[0] for s in structures))
        report['needsReview'].append(dict(glyph=dest, reason='Designer review of color, spacing, curves and interpolation required'))
        if set(masters) != {str(m.id) for m in font.masters}:
            report['needsReview'].append(dict(glyph=dest, reason='Unrequested masters need completion before export'))
    after = {n: digest(glyph_state(font.glyphs[n], masters)) for n in dependencies}
    for name in {r['source'] for r in rows} | (set(dependencies) - set(report['created'])):
        if guards[name] != after[name]:
            raise RuntimeError('Untargeted source/dependency changed: ' + name + '; inspect native recovery')
    report['resultGuards'] = after
    report['changesVerified'] = stage == 'construct'
    if stage == 'verify':
        expected = params.get('expected', {})
        report['changedSinceReview'] = [n for n, h in expected.items() if after.get(n) != h]
        report['changesVerified'] = bool(expected) and not report['changedSinceReview']
    report['nextActions'] = ['Review native proofs before expansion', 'Record designer decisions and manual corrections',
                              'Check sampled interpolation and language/feature behavior separately']
    if report_path:
        with open(report_path, 'x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    return report


if __name__ == '__main__':
    CAPS_REPORT = run_caps(font, params)
    print(json.dumps(CAPS_REPORT, ensure_ascii=False, allow_nan=False))
