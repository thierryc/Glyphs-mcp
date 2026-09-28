"""Exact kerning assignments; no collision policy or group expansion."""
from collections.abc import Mapping
import math
from .models import ProtocolError

WRITE_CAPABILITY = 'kerning.edit.exact.v1'
MAX_EDITS = 100
DIRECTIONS = {'LTR': 0, 'RTL': 2, 'vertical': 4}
# Native keys verified against Glyphs 4.1, including vertical T/B naming.
GROUPS = {'@MMK_L_': 'right', '@MMK_R_': 'left', '@MMK_T_': 'bottom', '@MMK_B_': 'top'}
SIDES = {'LTR': ('@MMK_L_', '@MMK_R_'), 'RTL': ('@MMK_R_', '@MMK_L_'),
         'vertical': ('@MMK_T_', '@MMK_B_')}


def fail(message, code='invalid_request'):
    raise ProtocolError(code, message)


def text(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 255 or value != value.strip() or '\x00' in value:
        fail('Kerning identities must be exact strings of 1-255 characters')
    return value


def number(value):
    if type(value) not in (int, float):
        fail('Kerning values must be finite numbers; zero is a stored value')
    try: finite = math.isfinite(value)
    except OverflowError: finite = False
    if not finite: fail('Kerning values must be finite numbers')
    return value


def validate_options(value):
    if not isinstance(value, Mapping) or set(value) != {'edits'}:
        fail('kerning_edit requires options.edits only')
    rows = value['edits']
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_EDITS:
        fail('kerning_edit requires 1-100 exact pair edits')
    result, seen = [], set()
    for row in rows:
        if not isinstance(row, Mapping) or row.get('op') not in ('set', 'remove'):
            fail('Kerning edits require op set or remove')
        required = {'op', 'master', 'direction', 'left', 'right'} | ({'value'} if row['op'] == 'set' else set())
        if set(row) != required or not isinstance(row.get('direction'), str) or row['direction'] not in DIRECTIONS:
            fail('Kerning edits require explicit master, direction and two sides; only set accepts value')
        master, direction = text(row['master']), row['direction']
        normalized, keys = {}, []
        for side, prefix in zip(('left', 'right'), SIDES[direction]):
            item = row[side]
            if not isinstance(item, Mapping) or item.get('kind') not in ('glyph', 'group'):
                fail('Each pair side requires kind glyph or group')
            field = 'name' if item['kind'] == 'glyph' else 'key'
            if set(item) != {'kind', field}: fail('Unexpected kerning side fields')
            key = text(item[field])
            if item['kind'] == 'glyph' and key.startswith('@'):
                fail('Use kind group for native group keys')
            if item['kind'] == 'group' and (not key.startswith(prefix) or len(key) == len(prefix)):
                fail('Group key does not match the requested side and direction: ' + key)
            normalized[side] = dict(item); keys.append(key)
        identity = (master, direction, *keys)
        if identity in seen: fail('Duplicate or conflicting kerning pair edits')
        seen.add(identity)
        result.append(dict(op=row['op'], master=master, direction=direction, **normalized,
                           **({'value': number(row['value'])} if row['op'] == 'set' else {})))
    return {'edits': result}


def glyph_state(glyph):
    return dict(glyph=text(str(glyph.name)), id=text(str(glyph.id)), groups=[
        getattr(glyph, side + 'KerningGroup', None) or None for side in ('left', 'right', 'top', 'bottom')])


def validate_guard(value):
    if not isinstance(value, Mapping) or set(value) != {'left', 'right'}:
        fail('Kerning target guard requires both sides')
    result = {}
    for side, state in value.items():
        if not isinstance(state, Mapping) or set(state) != {'glyph', 'id', 'groups'}:
            fail('Invalid kerning glyph identity guard')
        groups = state['groups']
        if not isinstance(groups, list) or len(groups) != 4:
            fail('Kerning identity guard requires four group names')
        result[side] = dict(glyph=text(state['glyph']), id=text(state['id']),
                            groups=[None if g is None else text(g) for g in groups])
    return result


def check_guard(font, target):
    # Group anchors provide bounded identity checks in addition to the shared
    # document-generation guard. Membership is never expanded into pair writes.
    for state in target.get('targetGuard', {}).values():
        glyph = font.glyphs[state['glyph']]
        if glyph is None or glyph_state(glyph) != state:
            fail('Kerning glyph identity or group assignment changed; prepare again', 'stale_target')


def read_stored(font, master, left, right, direction):
    table_name = {'LTR': 'kerningLTR', 'RTL': 'kerningRTL', 'vertical': 'kerningVertical'}[direction]
    if hasattr(font, table_name):
        keys=[]
        for key in (left,right):
            if key.startswith('@'): keys.append(key)
            else:
                glyph=font.glyphs[key]
                if glyph is None: fail('Kerning glyph is unavailable: '+key,'target_not_found')
                keys.append(str(glyph.id))
        # Direct native dictionary lookups preserve exact absence, including
        # values above the wrapper's numeric "not found" threshold.
        table=getattr(font,table_name)
        for key in (master,*keys):
            if table is None: return None
            table=table.objectForKey_(key)
        return None if table is None else number(float(table))
    # Plain model hosts have no Objective-C dictionary interface.
    return font.kerningForPair(master,left,right,direction=DIRECTIONS[direction])
