"""Bounded native-Python requests with a saved document baseline."""
import hashlib
import json
from collections.abc import Mapping

from .models import ProtocolError, canonical_json

NATIVE = 'script.native.v1'
MAX_TARGETS = 4096
MAX_SOURCE_BYTES = 128 * 1024
MAX_PARAMS_BYTES = 64 * 1024
MAX_OUTPUT_CHARS = 16000
WARNING = ('This script can access Glyphs and your computer. Restore saved version reloads '
           'the whole font and discards later unsaved edits. External effects are not restored.')


def retired(options):
    return bool({'executionMode', 'recovery'} & set(options))


def fail(message):
    raise ProtocolError('invalid_request', message)


def text(value, label, maximum=255):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        fail(f'{label} must be a nonempty string of at most {maximum} characters')
    return value


def json_value(value, maximum):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
    except (ValueError, TypeError, RecursionError) as error:
        fail('script data must be finite JSON: ' + str(error))
    if len(encoded.encode('utf-8')) > maximum:
        fail('script data exceeds its byte limit')
    return json.loads(encoded)


def target(value):
    if not isinstance(value, Mapping) or set(value) - {'glyph', 'layer', 'surface'}:
        fail('script targets require glyph, layer and optional surface')
    surface = value.get('surface', 'foreground')
    if surface not in ('foreground', 'background'):
        fail('script surface must be foreground or background')
    return dict(glyph=text(value.get('glyph'), 'glyph'), layer=text(value.get('layer'), 'layer'), surface=surface)


def targets(value):
    if not isinstance(value, list) or len(value) > MAX_TARGETS:
        fail('script targets must contain at most 4,096 surfaces')
    result = []
    seen = set()
    owners = {}
    for raw in value:
        item = target(raw)
        key = (item['glyph'], item['layer'], item['surface'])
        if key in seen:
            continue
        owner = key[:2]
        if owner in owners and owners[owner] != item['surface']:
            fail('select one surface per owning layer; foreground/background targets overlap')
        owners[owner] = item['surface']
        seen.add(key)
        result.append(item)
    return result


def validate_options(value):
    if not isinstance(value, Mapping):
        fail('python_script options must be an object')
    if retired(value):
        fail('executionMode and recovery are retired; prepare a new native script request with a saved baseline')
    if set(value) - {'source', 'params', 'entrypoint', 'targets', 'summary'}:
        fail('invalid python_script options')
    entrypoint = value.get('entrypoint', 'per_target')
    if entrypoint not in ('per_target', 'script'):
        fail('entrypoint must be per_target or script')
    source = text(value.get('source'), 'source', MAX_SOURCE_BYTES)
    if len(source.encode('utf-8')) > MAX_SOURCE_BYTES:
        fail('script source exceeds 128 KiB')
    try:
        # Compile only: decorators, defaults and module statements do not execute.
        compile(source, '<glyphs-mcp-script>', 'exec')
    except (SyntaxError, ValueError) as error:
        fail('script syntax error: ' + str(error))
    selected = value.get('targets', [])
    if isinstance(selected, Mapping):
        if set(selected) - {'master', 'glyphs', 'surface'} or 'master' not in selected:
            fail('bulk targets require an exact master ID, optional glyphs and surface')
        surface = selected.get('surface', 'foreground')
        if surface not in ('foreground', 'background'):
            fail('invalid bulk surface')
        names = selected.get('glyphs', 'all')
        if names != 'all':
            if not isinstance(names, list) or not 1 <= len(names) <= MAX_TARGETS:
                fail('bulk glyphs must be all or 1-4,096 names')
            names = list(dict.fromkeys(text(n, 'glyph') for n in names))
        selected = dict(master=text(selected['master'], 'master'), glyphs=names, surface=surface)
    else:
        selected = targets(selected)
    if not selected and entrypoint == 'per_target':
        fail('this script requires explicit targets')
    params = value.get('params', {})
    if not isinstance(params, Mapping):
        fail('params must be a JSON object')
    result = dict(source=source, params=json_value(dict(params), MAX_PARAMS_BYTES),
                  entrypoint=entrypoint, targets=selected)
    if 'summary' in value:
        result['summary'] = text(value['summary'], 'summary', 500)
    return result


def digest(value):
    return 'sha256:' + hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()
