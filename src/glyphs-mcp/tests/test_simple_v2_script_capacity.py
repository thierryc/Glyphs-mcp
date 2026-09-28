"""Larger script manifests stay complete, bounded, read-only and cancellable."""
import json
from types import SimpleNamespace

import pytest
from test_simple_v2_saved_scripts import env, start
from test_simple_v2_edit_workflow import wait, choose
from glyphs_mcp_protocol import scripts, script_targets, ProtocolError
from glyphs_mcp_bridge import saved_script
from glyphs_mcp_bridge.core import BridgeCore, BridgeError

LIMIT = 4 * 1024 * 1024


class Glyphs(dict):
    def __iter__(self):
        return iter(self.values())


def font_fixture(count, missing=0, stored_only=False, name=lambda i: 'g'+str(i)):
    class Glyph:
        def __init__(self, i):
            self.name = name(i)
            self.owner = SimpleNamespace(layerId='M', hasBackground=i >= missing,
                background=SimpleNamespace(shapes=[object()]))
        def countOfLayers(self): return 1
        def objectInLayersAtIndex_(self, index):
            assert index == 0
            return self.owner
        @property
        def layers(self):
            if stored_only: raise AssertionError('lazy layer iterator used')
            return [self.owner]
    glyphs = Glyphs((name(i), Glyph(i)) for i in range(count))
    return SimpleNamespace(glyphs=glyphs, masters=[SimpleNamespace(id='M')])


def opts(font, selector='all'):
    names = list(font.glyphs.keys())
    targets = ([dict(glyph=n, layer='M', surface='background') for n in names]
               if selector == 'explicit' else
               dict(master='M', glyphs=names if selector == 'names' else 'all', surface='background'))
    return dict(source='raise AssertionError("preparation executed Python")', targets=targets)


def request(options):
    return dict(jobId='capacity', documentId='doc', sourcePath='/fixture.glyphs',
                sourceHash='sha256:'+'a'*64, generation=1, options=options)


def core_fixture(font):
    queue = []
    state = dict(id='doc', path='/fixture.glyphs', generation=1, dirty=False)
    adapter = SimpleNamespace(_font=lambda _: font, document_state=lambda _: dict(state))
    core = BridgeCore(adapter, queue.append, chunk_limit=7)
    return core, queue, state


@pytest.mark.parametrize('count', [4096, 4097, 10000, 20000])
@pytest.mark.parametrize('selector', ['explicit', 'names', 'all'])
def test_large_selectors_cover_every_surface(count, selector):
    font = font_fixture(count)
    options = scripts.validate_options(opts(font, selector))
    selected, skipped = script_targets.resolve(font, options['targets'])
    assert [t['glyph'] for t, _ in selected] == list(font.glyphs.keys())
    assert skipped == dict(count=0, sample=[])


def test_resolution_never_uses_lazy_layer_iteration():
    font = font_fixture(10, missing=2, stored_only=True)
    selected, skipped = script_targets.resolve(font, opts(font)['targets'])
    assert len(selected) == 8 and skipped['count'] == 2
    with pytest.raises(ValueError, match='layer is unavailable'):
        script_targets.resolve(font, [dict(glyph='g0', layer='missing')])


def test_review_is_chunked_read_only_idempotent_and_compact():
    font = font_fixture(120, missing=50, stored_only=True)
    core, queue, state = core_fixture(font)
    r = request(opts(font))
    result = saved_script.review(core, r, BridgeError)
    assert result['status'] == 'preparing'
    assert saved_script.review(core, r, BridgeError) == result and len(queue) == 1
    queue.pop(0)()
    assert core.operation(r['jobId'])['status'] == 'preparing'
    assert state['dirty'] is False
    while queue: queue.pop(0)()
    result = saved_script.review_result(core, r['jobId'], BridgeError)
    assert result['targetCount'] == 70 and result['skippedCount'] == 50
    assert len(result['targets']) == 10 and len(result['manifest']) == 70
    assert len(json.dumps(core.operation(r['jobId']))) < 2000
    assert 'scriptResult' not in result


@pytest.mark.parametrize('change', ['cancel', 'generation', 'closed'])
def test_preparation_can_stop_without_module_execution(change):
    core, queue, state = core_fixture(font_fixture(100))
    r = request(opts(core.adapter._font('doc')))
    saved_script.review(core, r, BridgeError)
    queue.pop(0)()
    if change == 'cancel': core.discard(r['jobId'])
    elif change == 'generation': state['generation'] += 1
    else:
        def closed(_): raise BridgeError('document_not_found', 'closed')
        core.adapter.document_state = closed
    while queue: queue.pop(0)()
    result = core.operation(r['jobId'])
    assert result['status'] == ('cancelled' if change == 'cancel' else 'failed')
    assert not result.get('scriptResult')
    assert 'prepareIterator' not in core._operations[r['jobId']]


def test_large_manifest_rejected_during_review_with_bounded_retention():
    font = font_fixture(20000, name=lambda i: ('字' * 240)+str(i))
    core, queue, _ = core_fixture(font)
    r = request(opts(font))
    saved_script.review(core, r, BridgeError)
    while queue: queue.pop(0)()
    result = core.operation(r['jobId'])
    assert result['status'] == 'failed' and result['error']['code'] == 'request_too_large'
    assert not core._operations[r['jobId']].get('preparedReport')


def test_oversized_complete_request_never_saves_or_runs(env):
    service, bridge, _ = env
    bridge.adapter.dirty = True
    value = wait(service, start(service), 'waiting_run')
    report = service.jobs.read_json(value['jobId'], 'report.json')
    report['manifest'] = [dict(glyph='字'*250+str(i), layer='M', surface='foreground') for i in range(6000)]
    service.jobs.write_json(value['jobId'], 'report.json', report)
    value = choose(service, value, 'save_run_script')
    assert value['error']['code'] == 'request_too_large'
    assert not bridge.adapter.save_calls and not bridge.runs


def test_byte_boundary_uses_the_complete_actual_utf8_envelope():
    options = dict(source='#字\\\"\n' * 20, params={'note':'é'}, entrypoint='script', targets=[])
    r = dict(request(options), manifest=[])
    # The boundary includes the outer script wrapper and JSON escaping.
    actual = lambda: json.dumps({'script':r}, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    r['sourcePath'] += 'x' * (LIMIT - len(actual()))
    assert len(actual()) == LIMIT
    assert scripts.check_request(r) == LIMIT
    r['sourcePath'] += 'x'
    with pytest.raises(ProtocolError) as failure: scripts.check_request(r)
    assert failure.value.code == 'request_too_large'


def test_retained_non_script_limits():
    from glyphs_mcp_protocol import outline, native_actions
    assert outline.MAX_NODES == outline.MAX_LAYER_CHANGES == 4096
    assert native_actions.MAX_LAYER_CHANGES == 4096
    assert scripts.MAX_SOURCE_BYTES == 128*1024 and scripts.MAX_PARAMS_BYTES == 64*1024
    assert scripts.MAX_OUTPUT_CHARS == 16000


def executable_fixture(tmp_path, monkeypatch, count=4097):
    font = font_fixture(count, stored_only=True)
    core, queue, state = core_fixture(font)
    path = tmp_path/'baseline.glyphs'; path.write_text('saved fixture')
    state['path'] = str(path)
    font.parent = SimpleNamespace(updateChangeCount_=lambda _: state.update(dirty=True))
    for glyph in font.glyphs.values(): glyph.owner.background.visits = 0
    adapter = core.adapter
    adapter.begin_undo = adapter.end_undo = lambda *a: None
    adapter._operation_font = adapter._font
    adapter._native_identity = id
    adapter._rounding_states = {}
    adapter.glyphs = None
    adapter.script_target = lambda doc, target: (script_targets.owner(font, target).background, None)
    monkeypatch.setattr(saved_script, 'available', lambda: True)
    options = scripts.validate_options(dict(opts(font), source='def run(layer, params, context):\n    layer.visits += 1'))
    from glyphs_mcp_protocol.source_identity import source_hash
    r = dict(request(options), sourcePath=str(path), sourceHash=source_hash(path),
             manifest=[t for t, _ in script_targets.resolve(font, options['targets'])[0]])
    return core, queue, state, font, r


def test_large_execution_is_exactly_once_and_does_not_require_worker(tmp_path, monkeypatch):
    core, queue, state, font, r = executable_fixture(tmp_path, monkeypatch, 10000)
    result = core.begin_script(r)
    assert core.begin_script(r) == result
    assert not state['dirty'] and len(queue) == 1
    while queue: queue.pop(0)()
    result = core.operation(r['jobId'])
    assert result['status'] == 'applied' and result['scriptResult']['executedTargets'] == 10000
    assert core.begin_script(r) == result and not queue
    assert all(g.owner.background.visits == 1 for g in font.glyphs.values())


@pytest.mark.parametrize('stop', ['cancel_before', 'cancel_after', 'stale', 'removed'])
def test_execution_revalidation_and_cancellation_never_replay(tmp_path, monkeypatch, stop):
    core, queue, state, font, r = executable_fixture(tmp_path, monkeypatch)
    core.begin_script(r)
    if stop == 'cancel_after':
        while not core.operation(r['jobId'])['scriptResult']['executedTargets']:
            queue.pop(0)()
    else: queue.pop(0)()
    if stop.startswith('cancel'): core.discard(r['jobId'])
    elif stop == 'stale': state['generation'] += 1
    else: font.glyphs['g4096'].owner.hasBackground = False
    while queue: queue.pop(0)()
    result = core.operation(r['jobId'])
    assert result['status'] == ('cancelled' if stop.startswith('cancel') else 'failed')
    assert result['scriptResult']['executed'] == (stop == 'cancel_after')
    visits = sum(g.owner.background.visits for g in font.glyphs.values())
    assert visits == result['scriptResult']['executedTargets'] < 4097
    assert bool(visits) == (stop == 'cancel_after')
    assert core.begin_script(r) == result and not queue


def test_ordinary_bulk_named_polling_is_bounded(env):
    service, bridge, _ = env
    names = ['glyph'+str(i) for i in range(20000)]
    value = service.edit_workflows.start('doc_1', kind='python_script', idempotency_key='large-named',
        options=dict(source='pass', targets=dict(master='M', glyphs=names, surface='background')))
    value = wait(service, value, 'waiting_run')
    assert len(value['scope']['targets']['glyphs']) <= 100
    assert value['scope']['targetSelectorGlyphCount'] == 20000
    assert len(json.dumps(value)) < 20000
    details = service.edit_workflows.get(value['id'], include_review=True)
    assert details['scriptReview']['targets']['glyphs'] == names


def test_stale_private_runtime_requires_update_without_fallback(env):
    service, bridge, _ = env
    bridge.status = lambda: dict(jobCapabilities=[scripts.NATIVE])
    from glyphs_mcp_sidecar.service import ServiceError
    with pytest.raises(ServiceError, match='coordinated runtime update'): start(service)
    assert not bridge.reviews and not bridge.runs and not bridge.adapter.save_calls


def test_manifest_budget_matches_wire_bytes_with_duplicated_explicit_targets():
    rows = [dict(glyph='字\\"'+str(i), layer='master-é', surface='background') for i in range(100)]
    options = scripts.validate_options(dict(source='pass', entrypoint='script', targets=rows, params={'x':'é'}))
    r = request(options)
    budget = scripts.ManifestBudget(r)
    for index, row in enumerate(rows, 1):
        budget.add(row)
        assert budget.size == scripts.check_request(dict(r, manifest=rows[:index]))
