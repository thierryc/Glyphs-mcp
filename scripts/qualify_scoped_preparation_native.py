"""M2 native parity, exact unnamed-node recovery and retained worker qualification."""
import json
from copy import deepcopy
from pathlib import Path
import sys
from native_script_harness import Harness, GSFontMaster
from GlyphsApp import GSComponent, GSAnchor
from glyphs_mcp_sidecar.native_worker import _load_font
from glyphs_mcp_protocol.preparation import stored_layers
from glyphs_mcp_protocol.preparation.simple import CAPABILITY
from glyphs_mcp_protocol.preparation.outline import _path_state, _shape_state, _value
from glyphs_mcp_protocol.outline import path_hash
from glyphs_mcp_protocol import dimensions

args = [a for a in sys.argv[1:] if a != '--']
suffix, output = args
h = Harness(count=3, contours=2, suffix=suffix, single_master=True)


def differences(left, right, path=''):
    if type(left) is type(right) and isinstance(left, dict) and left.keys() == right.keys():
        return sum((differences(left[k], right[k], path+'/'+str(k)) for k in left), [])
    if type(left) is type(right) and isinstance(left, (list, tuple)) and len(left) == len(right):
        return sum((differences(a, b, path+'/'+str(i)) for i, (a, b) in enumerate(zip(left, right))), [])
    return [] if left == right else [dict(path=path, before=left, after=right)]


def exercise(h):
    def setup():
        font = h.doc.font
        h.doc.undoManager().beginUndoGrouping()
        for g in font.glyphs: g.undoManager().beginUndoGrouping()
        second = GSFontMaster(); second.name = 'Other'; font.masters.append(second)
        for g in font.glyphs:
            first = g.layers[h.mid]
            first.shapes = [s.copy() for s in first.background.shapes]
            first.anchors.append(GSAnchor('top', (125.25, 700.5)))
            first.userData['qualification'] = 'preserve'
            other = g.layers[second.id]
            other.shapes = [s.copy() for s in first.shapes]
            other.width = 600.25
            for layer in (first, first.background, other):
                for pi, path in enumerate(layer.paths):
                    for ni, node in enumerate(path.nodes): node.setName_(None if ni == 0 else '' if ni == 1 else f'point-{pi}-{ni}')
        font.glyphs['probe0'].layers[h.mid].shapes.append(GSComponent('probe2'))
        key = next(iter(dimensions.CATALOG))
        font.userData[dimensions.STORAGE_KEY] = {h.mid: {key: 40.25}}
        font.save(str(h.source), makeCopy=True)
        # Use the actual serialized baseline on both routes, including native defaults.
        h.doc.setFont_(_load_font(h.source, preserve_grid=True))
        h.clean()
        return str(second.id), key
    other, dimension_key = h.main(setup)
    document = h.service.list_documents()[0]['id']
    status = h.service.bridge.status
    route = ['native']
    def routed_status():
        value = status()
        if route[0] == 'worker':
            value['jobCapabilities'] = [c for c in value['jobCapabilities'] if c != CAPABILITY]
        return value
    h.service.bridge.status = routed_status

    def observe():
        font = h.doc.font
        return dict(glyphs={str(g.name): dict(color=None if g.color is None else int(g.color),
            layers={str(l.layerId): dict(width=float(l.width), foreground=_shape_state(l),
                background=_shape_state(l.background) if _value(l, 'hasBackground', False) else None,
                anchors=[(str(a.name), float(a.position.x), float(a.position.y)) for a in l.anchors],
                userData=dict(l.userData)) for l in stored_layers(g)}) for g in font.glyphs},
            dimensions=dimensions.read_state(font.userData[dimensions.STORAGE_KEY], h.mid, dimension_key))

    def outline(surface, scope='ids'):
        layer = h.doc.font.glyphs['probe0'].layers[h.mid]
        selected = layer.background if surface == 'background' else layer
        return dict(kind='outline_edit', options=dict(compatibilityPolicy='preserve', targets=[dict(
            glyph='probe0', surface=surface, referenceLayer=h.mid,
            layers=dict(scope='all_masters') if scope == 'all_masters' else dict(scope='ids', ids=[h.mid]),
            guards=[dict(path=0, hash=path_hash(_path_state(selected.paths[0])))],
            operations=[dict(op='update_nodes', path=0, updates=[dict(index=0, delta=dict(dx=.25, dy=.5))])])]))

    cases = [('width-selected-two-masters', dict(kind='width_delta', glyphs=['probe0'], delta=.25)),
        ('glyph-color', dict(kind='native_action', options=dict(action='set_glyph_color',
            arguments=dict(color='red'), targets=[dict(glyph='probe0')]))),
        ('dimensions-overwrite', dict(kind='dimensions_edit', options=dict(changes=[dict(
            master=h.mid, key=dimension_key, value=41.5)]))),
        ('foreground-components', h.main(lambda: outline('foreground'))),
        ('foreground-all-masters', h.main(lambda: outline('foreground', 'all_masters'))),
        ('background-preserve-foreground', h.main(lambda: outline('background')))]
    results = []
    for name, request in cases:
        before = h.main(observe)
        expected = deepcopy(before)
        glyph = expected['glyphs']['probe0']
        if name.startswith('width'):
            for layer in glyph['layers'].values(): layer['width'] += .25
        elif name == 'glyph-color': glyph['color'] = 0
        elif name == 'dimensions-overwrite': expected['dimensions'] = dict(present=True, value=41.5)
        else:
            surface = 'background' if name.startswith('background') else 'foreground'
            for mid in ([h.mid, other] if name.endswith('all-masters') else [h.mid]):
                node = glyph['layers'][mid][surface][0]['nodes'][0]
                node['x'] += .25; node['y'] += .5
        prepared = []
        for chosen in ('worker', 'native'):
            route[0] = chosen
            value = h.service.edit_workflows.start(document, mode='preview', auto_keep=False,
                idempotency_key=name+'-'+chosen, **request)
            value = h.wait(value, 'ready', 'needs_review')
            job_id = value['jobId']
            patch = h.service.jobs.read_json(job_id, 'patch.json')
            report_path = h.service.jobs.path(job_id) / 'report.json'
            prepared.append((patch['changes'], json.loads(report_path.read_text()) if report_path.exists() else None))
            assert h.main(observe) == before, (name, chosen, 'live mutation during preparation')
            assert not h.service.list_documents()[0]['dirty']
            if chosen == 'native': assert not list(h.service.jobs.path(job_id).glob('source*'))
            apply = next(a for a in value['actions'] if a['action'] == 'apply')
            approvals = prepared[-1][1].get('requiredOverwrites') if prepared[-1][1] else None
            value = h.wait(h.service.edit_workflows.respond(value['id'], value['revision'], apply['token'],
                approved_overwrites=approvals), 'applied')
            assert h.main(observe) == expected, (name, chosen, 'application or control mismatch')
            def undo_redo():
                manager = h.doc.undoManager() if name.startswith('dimensions') else h.doc.font.glyphs['probe0'].undoManager()
                assert manager.canUndo();manager.undo()
                assert observe() == before, (name, chosen, 'native Undo mismatch', differences(before, observe()))
                assert manager.canRedo();manager.redo()
                assert observe() == expected, (name, chosen, 'native Redo mismatch')
            h.main(undo_redo)
            h.wait(h.choose(value, 'discard'), 'discarded')
            recovered = h.main(observe)
            assert recovered == before, (name, chosen, 'selective recovery mismatch', differences(before, recovered))
            h.main(h.clean)
        assert prepared[0] == prepared[1], (name, 'route semantics differ', prepared)
        if name == 'dimensions-overwrite': assert prepared[1][1]['requiredOverwrites']
        results.append(dict(case=name, matchingPatchAndReport=True, preparationReadOnly=True,
            targetedApplicationAndUntouchedControls=True, selectiveRecovery=True))

    def color_metadata():
        from types import SimpleNamespace
        from GlyphsApp import GSGlyph
        from glyphs_mcp_protocol.preparation import consume, native_action
        from glyphs_mcp_protocol.native_actions import GLYPH_COLOR_INDEX
        for color in GLYPH_COLOR_INDEX.values():
            g=GSGlyph('A');g.color=color;g.note='preserve';g.userData['nested']={'keep':[1,2]}
            g.leftKerningGroup='A';g.leftMetricsKey='=H'
            for wanted in ('orange','none'):
                request=dict(options=dict(action='set_glyph_color',arguments=dict(color=wanted),targets=[dict(glyph='A')]))
                original=native_action.persistent_state(g,'glyph')
                expected=native_action.prepare(SimpleNamespace(glyphs={'A':g.copy()}),request)
                actual=consume(native_action.prepare_iter(SimpleNamespace(glyphs={'A':g}),request,detached=True))
                assert actual==expected
                assert native_action.persistent_state(g,'glyph')==original
        g.colorObject=(.2,.3,.4,1.)
        original=native_action.persistent_state(g,'glyph')
        try:consume(native_action.prepare_iter(SimpleNamespace(glyphs={'A':g}),request,detached=True))
        except native_action.WorkerError as exc:assert 'custom glyph color' in str(exc)
        else:raise AssertionError('custom color was lost by metadata-only copy')
        assert native_action.persistent_state(g,'glyph')==original
        return True
    assert h.main(color_metadata)
    results.append(dict(case='all-palette-colors-and-clear',matchingPatchAndReport=True,
        customColorRejectedBeforeCopy=True,nestedMetadataPreserved=True,preparationReadOnly=True))

    # A missing background must be rejected without invoking its lazy getter.
    route[0] = 'native'
    req = h.main(lambda: outline('background'))
    req['options']['targets'][0]['layers']['ids'] = [other]
    before = h.main(observe)
    value = h.service.edit_workflows.start(document, mode='preview', auto_keep=False,
        idempotency_key='missing-background', **req)
    value = h.wait(value, 'failed')
    assert h.main(observe) == before
    assert h.main(lambda: not _value(h.doc.font.glyphs['probe0'].layers[other], 'hasBackground', False))
    assert not h.service.list_documents()[0]['dirty']
    results.append(dict(case='missing-background', rejectedWithoutCreation=True, error=value.get('error')))
    return dict(format=suffix, checks=results, grid=1, masters=2,
        mixedNamedAndAbsentNodes=True, nativeUndoRedo=True, exactNameRestoration=True)


result = h.run(exercise)
Path(output).write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result), flush=True)
if not result.get('passed'): raise RuntimeError(result.get('error'))
