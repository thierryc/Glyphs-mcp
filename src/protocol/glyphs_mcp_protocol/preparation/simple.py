"""Closed selection and shared patch construction for inexpensive typed jobs."""
import json
import math
from . import PreparationError, consume, stored_layers
from ..models import MAX_CHANGES, PATCH_VERSION, validate_patch, ProtocolError

CAPABILITY = 'edit.prepare.native.v1'


def eligible(request):
    kind, options = request.get('kind'), request.get('options') or {}
    if kind in {'width_delta', 'dimensions_edit', 'kerning_edit'}:
        return True
    if kind == 'native_action':
        return options.get('action') == 'set_glyph_color' and options.get('scope') == 'glyph'
    if kind == 'outline_edit':
        targets = options.get('targets') or []
        return bool(targets) and all(t.get('operations') and all(
            op.get('op') == 'update_nodes' and op.get('updates') and all(
                set(u) <= {'index', 'position', 'delta'} and ('position' in u or 'delta' in u)
                for u in op['updates']) for op in t['operations']) for t in targets)
    return False


def validate_request(request):
    if not isinstance(request, dict) or not eligible(request):
        raise ProtocolError('invalid_request', 'request is not eligible for native typed preparation')
    kind = request['kind']
    if kind == 'width_delta':
        if set(request) != {'kind', 'glyphs', 'delta'}:
            raise ProtocolError('invalid_request', 'unexpected width request fields')
        delta, names = request['delta'], request['glyphs']
        if (isinstance(delta, bool) or not isinstance(delta, (float, int)) or not math.isfinite(delta) or delta == 0
                or not isinstance(names, list) or len(names) > 10000
                or any(not isinstance(n, str) or not n for n in names) or len(names) != len(set(names))):
            raise ProtocolError('invalid_request', 'invalid width delta or glyph names')
    else:
        if set(request) != {'kind', 'glyphs', 'options'} or request['glyphs']:
            raise ProtocolError('invalid_request', 'unexpected typed request fields')
        from .. import outline, native_actions, dimensions, kerning_edits
        validator = {'outline_edit': outline, 'native_action': native_actions, 'dimensions_edit': dimensions, 'kerning_edit': kerning_edits}[kind]
        options = dict(request['options'])
        if kind == 'native_action':
            scope = options.pop('scope', None)
            if validator.validate_options(options)['scope'] != scope:
                raise ProtocolError('invalid_request', 'native action normalized scope is inconsistent')
        else:
            validator.validate_options(options)
    return request


def number(value):
    value = float(value)
    return int(value) if value.is_integer() else value


def width_iter(font, request):
    names = set(request.get('glyphs') or [])
    missing, changes = set(names), []
    selected = font.glyphs
    if names:
        selected = []
        # Plain collections support the same algorithm in non-native hosts.
        # Native Glyphs uses its name index, without walking unrelated glyphs.
        plain = ({str(g.name): (i, g) for i, g in enumerate(font.glyphs)}
                 if type(font.glyphs) in (list, tuple) else None)
        for name in request['glyphs']:
            try:
                glyph = plain.get(name, (None, None))[1] if plain is not None else font.glyphs[name]
            except KeyError:
                glyph = None
            if glyph is not None and str(glyph.name or '') == name:
                selected.append(glyph)
                missing.discard(name)
            yield
        if missing:
            raise ValueError('width_delta requested glyphs missing from saved source: ' + json.dumps(sorted(missing), ensure_ascii=False))
        index = getattr(font, 'indexOfGlyph_', None)
        if callable(index):
            selected.sort(key=index)
        elif plain is not None:
            selected.sort(key=lambda g: plain[str(g.name)][0])
    for glyph in selected:
        name = str(glyph.name or '')
        missing.discard(name)
        if not name or names and name not in names:
            yield
            continue
        for layer in stored_layers(glyph):
            identity = str(layer.layerId or layer.associatedMasterId or '')
            if identity:
                before = number(layer.width)
                after = number(float(before) + float(request['delta']))
                if after != before:
                    changes.append(dict(kind='set', glyph=name, layer=identity, field='width', before=before, after=after))
                    if len(changes) > MAX_CHANGES:
                        raise PreparationError('width job exceeds the existing patch change limit')
            yield
    if missing:
        raise PreparationError('width_delta requested glyphs missing from saved source: ' + json.dumps(sorted(missing), ensure_ascii=False))
    if not changes:
        raise ValueError('the job selected no writable layers')
    return changes, None


def iterator(font, request):
    validate_request(request)
    if request['kind'] == 'width_delta':
        return width_iter(font, request)
    from . import dimensions, outline, native_action, kerning
    if request['kind'] == 'kerning_edit':
        return kerning.prepare_iter(font, request)
    if request['kind'] == 'dimensions_edit':
        return dimensions.prepare_iter(font, request)
    if request['kind'] == 'outline_edit':
        return outline.prepare_iter(font, request, stored_only=True)
    return native_action.prepare_iter(font, request, detached=True)


def summary(request, changes, report):
    kind = request['kind']
    if kind == 'width_delta':
        return 'Add {} units to {}'.format(number(request['delta']), 'selected glyphs' if request.get('glyphs') else 'all layers')
    if kind == 'outline_edit': return 'Outline edits for {} layers'.format(len(report['layers']))
    if kind == 'dimensions_edit': return 'Dimensions reference edits for {} fields'.format(len(report['targets']))
    if kind == 'kerning_edit': return 'Exact kerning edits for {} pairs'.format(len(report['pairs']))
    return 'Native {} action for {} targets'.format(report['action'], report['targetCount'])


def patch(job_id, document, fingerprint, request, changes, report):
    return validate_patch(dict(version=PATCH_VERSION, jobId=job_id, documentId=document['id'],
        sourcePath=document['path'], sourceHash=fingerprint, generation=document['generation'],
        changes=changes, summary=summary(request, changes, report)))
