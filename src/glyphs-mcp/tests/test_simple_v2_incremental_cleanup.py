"""Native cleanup yields without publishing success or releasing ownership early."""
from types import SimpleNamespace as NS

import pytest

from test_simple_v2_bridge import BridgeCore, BridgeError, QueueScheduler, patch
from test_simple_v2_glyphs_adapter import adapter, FractionalLayer, ListCollection
from test_simple_v2_exact_history import History
from glyphs_mcp_bridge.native_undo import NativeUndoScope


def fixture(count=31, *, bad_manager=False, bad_rounding=False):
    layers = [FractionalLayer() for _ in range(count)]
    managers = [History() for _ in layers]
    native, _ = adapter(layers[0])
    document = native.list_documents()[0]
    glyphs = native._font(document['id']).glyphs.values
    glyphs.clear()
    for index, (layer, manager) in enumerate(zip(layers, managers)):
        layer.undoManager = lambda m=manager: m
        glyphs['g'+str(index)] = NS(name='g'+str(index), layers=ListCollection([layer]))
    if bad_manager:
        def fail_name(_): raise RuntimeError('cleanup name failure')
        managers[-1].setActionName_ = fail_name
    if bad_rounding:
        original = native._set_rounding
        native._set_rounding = lambda layer, value: False if layer is layers[-1] and not value else original(layer, value)
    request = patch(count)
    request.update(documentId=document['id'], sourcePath=document['path'], generation=document['generation'])
    for change in request['changes']: change.update(before=727.3, after=727.675)
    queue = QueueScheduler(); core = BridgeCore(native, queue, chunk_limit=3)
    return core, queue, native, layers, managers, request


def cleanup_count(layers, managers):
    return sum(m.events.count('end') for m in managers) + sum(not l.temporarilyDisableRounding for l in layers)


@pytest.mark.parametrize('outcome', ['applied', 'cancelled', 'failed'])
def test_cleanup_is_bounded_and_keeps_ownership_until_last_step(outcome):
    core, queue, native, layers, managers, request = fixture()
    core.begin_apply(request)
    if outcome == 'cancelled':
        queue.run_one(); core.discard(request['jobId'])
    elif outcome == 'failed':
        layers[-1]._width = 900  # Later conflict: preceding writes must roll back.
    observed_cleanup = False
    while queue.items:
        before = cleanup_count(layers, managers)
        queue.run_one()
        result = core.operation(request['jobId'])
        delta = cleanup_count(layers, managers)-before
        assert delta <= core.chunk_limit, 'native cleanup ran all targets in one turn'
        if delta and queue.items:
            observed_cleanup = True
            assert result['status'] in {'applying','rolling_back'}
            assert core._operations[request['jobId']]['finishedAt'] is None
            assert core.status()['activeOperations'] == 1
            assert core.begin_apply(request)['status'] == result['status']
            with pytest.raises(BridgeError, match='another operation'):
                core._check_owner(request['documentId'])
            with pytest.raises(BridgeError): core.finish_edit(request['jobId'])
    assert observed_cleanup
    assert result['status'] == outcome
    assert all(m.level == 0 and m.automatic for m in managers)
    assert all(not layer.temporarilyDisableRounding for layer in layers)
    assert not native._operation_fonts and not native._operation_layers and not native._rounding_states
    assert not native._undo_managers
    assert core.status()['activeOperations'] == 0
    if outcome == 'applied':
        assert all(l.width == 727.675 for l in layers)
        for manager in managers: manager.undo()
        assert all(l.width == 727.3 for l in layers)
        for manager in managers: manager.undo()  # Fake history re-registers native Redo.
        assert all(l.width == 727.675 for l in layers)
        core.discard(request['jobId']); queue.drain()
        assert core.operation(request['jobId'])['status'] == 'discarded'
        assert all(l.width == 727.3 for l in layers)
    else:
        assert all(l.width == (900 if outcome == 'failed' and l is layers[-1] else 727.3) for l in layers)


@pytest.mark.parametrize('failure', ['manager', 'rounding', 'rounding_exception'])
def test_cleanup_error_does_not_skip_other_groups_or_flags(failure):
    core, queue, native, layers, managers, request = fixture(bad_manager=failure=='manager', bad_rounding=failure=='rounding')
    if failure == 'rounding_exception':
        setter = native._set_rounding
        def failing_setter(layer, value):
            if layer is layers[-1] and not value: raise RuntimeError('closed native layer')
            return setter(layer, value)
        native._set_rounding = failing_setter
    core.begin_apply(request)
    while queue.items:
        before = cleanup_count(layers, managers);queue.run_one()
        assert cleanup_count(layers, managers)-before <= core.chunk_limit
    result = core.operation(request['jobId'])
    assert result['status'] == 'failed' and 'cleanup' in result['error']['details']
    assert all(m.level == 0 and m.automatic and m.events.count('end') == 1 for m in managers)
    assert all(not l.temporarilyDisableRounding for l in layers[:-1])
    assert not native._operation_fonts and not native._operation_layers and not native._rounding_states
    assert core.begin_apply(request) == result  # Reconnect/duplicate never repeats cleanup.


def test_scope_closes_in_reverse_order_without_copying_all_managers():
    class NoBulkCopy(dict):
        def values(self): raise AssertionError('cleanup must not copy all managers')
    managers = [History() for _ in range(9)]
    closed = []
    for index, manager in enumerate(managers):
        def end(m=manager, i=index):
            closed.append(i)
            History.endUndoGrouping(m)
        manager.endUndoGrouping = end
    scope = NativeUndoScope()
    for manager in managers: scope.manager_for(NS(undoManager=lambda m=manager:m))
    scope.managers = NoBulkCopy(scope.managers)
    scope.finish('Finish')
    assert closed == list(reversed(range(9)))
    assert all(m.level == 0 and m.automatic for m in managers)
    assert not scope.managers


def test_cancel_during_completed_edit_cleanup_does_not_reopen_or_reapply():
    core, queue, native, layers, managers, request = fixture()
    core.begin_apply(request)
    while not any(m.events.count('end') for m in managers): queue.run_one()
    core.discard(request['jobId'])  # All writes finished; cleanup is compulsory.
    queue.drain()
    assert core.operation(request['jobId'])['status'] == 'applied'
    assert all(l.width == 727.675 for l in layers)
    assert all(m.events.count('begin') == m.events.count('end') == 1 for m in managers)
    assert core.finish_edit(request['jobId'])['status'] == 'completed'
    assert all(m.actions for m in managers)  # Keep does not erase native history.


def test_cleanup_respects_elapsed_budget_as_well_as_batch_bound(monkeypatch):
    from glyphs_mcp_bridge import core as module
    core, queue, native, layers, managers, request = fixture()
    core.begin_apply(request)
    while 'cleanupSteps' not in core._operations[request['jobId']]: queue.run_one()
    clock = [0.0]
    def tick():
        clock[0] += .006
        return clock[0]
    monkeypatch.setattr(module.time, 'perf_counter', tick)
    before = cleanup_count(layers, managers)
    queue.run_one()
    assert cleanup_count(layers, managers)-before == 1
    assert core.status()['activeOperations'] == 1
    queue.drain()
    assert core.operation(request['jobId'])['status'] == 'applied'


@pytest.mark.parametrize('outcome', ['success','failure','cancel'])
def test_script_cleanup_retains_owner_and_never_replays(tmp_path, monkeypatch, outcome):
    from test_simple_v2_script_capacity import executable_fixture
    core, queue, state, font, request = executable_fixture(tmp_path, monkeypatch, count=80)
    flags = {id(g.owner.background): (g.owner.background, False) for g in font.glyphs.values()}
    core.adapter._rounding_states = {request['documentId']: flags}
    released = []
    core.adapter._set_rounding = lambda layer, value: released.append(id(layer)) or True
    if outcome == 'failure':
        request['options']['source'] = 'def run(layer, params, context):\n    layer.visits += 1\n    if context["index"] == 5: raise ValueError("partial")'
    core.begin_script(request)
    if outcome == 'cancel':
        while not core.operation(request['jobId'])['scriptResult']['executedTargets']: queue.pop(0)()
        core.discard(request['jobId'])
    saw_cleanup = False
    while queue:
        count = len(released); queue.pop(0)()
        assert len(released)-count <= core.chunk_limit
        result = core.operation(request['jobId'])
        if len(released) > count and queue:
            saw_cleanup = True
            assert result['status'] == 'applying'
            assert core.begin_script(request)['status'] == 'applying'
            with pytest.raises(BridgeError): core._check_owner('other_document')
    assert saw_cleanup and len(released) == len(set(released))
    assert result['status'] == {'success':'applied','failure':'failed','cancel':'cancelled'}[outcome]
    assert not flags
    visits = sum(g.owner.background.visits for g in font.glyphs.values())
    assert core.begin_script(request) == result and not queue
    assert sum(g.owner.background.visits for g in font.glyphs.values()) == visits


def test_scheduler_failure_still_restores_all_native_settings_once():
    core, queue, native, layers, managers, request = fixture()
    core.begin_apply(request)
    while core.operation(request['jobId'])['completedChanges'] < len(layers): queue.run_one()
    def rejected(_): raise RuntimeError('scheduler stopped')
    core.schedule = rejected
    queue.drain()
    result = core.operation(request['jobId'])
    assert result['status'] == 'failed'
    assert all(m.level == 0 and m.automatic and m.events.count('end') == 1 for m in managers)
    assert all(not l.temporarilyDisableRounding for l in layers)
    assert core.status()['activeOperations'] == 0
