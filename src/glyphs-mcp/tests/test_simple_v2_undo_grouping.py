"""Own one native group, without disturbing existing UI history/settings."""
from types import SimpleNamespace as NS

import pytest

from test_simple_v2_glyphs_adapter import UndoManager, adapter
from glyphs_mcp_bridge.native_undo import NativeUndoScope


@pytest.mark.parametrize('automatic', [True, False])
def test_only_used_managers_are_grouped_and_settings_are_restored(automatic):
    document, glyph = UndoManager(), UndoManager()
    glyph.automatic = automatic
    scope = NativeUndoScope(document)
    layer = NS(undoManager=lambda: glyph)
    assert scope.manager_for(layer) is scope.manager_for(layer)
    assert glyph.level == 1 and not glyph.automatic
    assert document.level == 0 and document.events == []
    scope.finish('Edit')
    assert glyph.level == 0 and glyph.automatic == automatic
    assert glyph.events == ['begin', 'Edit', 'end']
    assert document.events == []


def test_document_fallback_still_groups_operations_that_use_it():
    document = UndoManager()
    scope = NativeUndoScope(document)
    assert scope.manager_for(None) is document
    assert document.level == 1 and not document.automatic
    scope.finish('Group kerning')
    assert document.level == 0 and document.automatic


def test_preexisting_group_is_refused_without_changing_it():
    manager = UndoManager();manager.level = 1
    scope = NativeUndoScope(manager)
    with pytest.raises(RuntimeError, match='finish the active edit'):
        scope.manager_for(None)
    scope.finish('Unused')
    assert manager.level == 1 and manager.automatic and manager.events == []


def test_failed_group_configuration_restores_original_setting():
    class Partial(UndoManager):
        def setGroupsByEvent_(self, value):
            self.automatic = value
            if not value: raise RuntimeError('setting failed after mutation')
    manager = Partial()
    with pytest.raises(RuntimeError, match='setting failed'):
        NativeUndoScope(manager).manager_for(None)
    assert manager.level == 0 and manager.automatic and manager.events == []


def test_finish_failure_still_closes_owned_groups_and_restores_all_settings():
    class BadName(UndoManager):
        def setActionName_(self, name): raise RuntimeError('name failed')
    first, second = UndoManager(), BadName()
    scope = NativeUndoScope()
    for m in (first, second):scope.manager_for(NS(undoManager=lambda m=m:m))
    with pytest.raises(RuntimeError, match='name failed'):scope.finish('Edit')
    assert all(m.level == 0 and m.automatic for m in (first, second))
    assert scope.managers == {}


def test_foreign_nested_group_is_not_closed_by_cleanup():
    manager = UndoManager();scope = NativeUndoScope(manager);scope.manager_for(None)
    manager.level += 1
    with pytest.raises(RuntimeError, match='grouping changed'):scope.finish('Edit')
    assert manager.level == 2 and manager.automatic
    assert manager.events == ['begin']


@pytest.mark.parametrize('cancel', [True, False])
def test_native_settings_survive_chunked_completion_and_cancellation(cancel):
    from test_simple_v2_bridge import BridgeCore, QueueScheduler, patch
    a, layer = adapter();manager = UndoManager();layer.undoManager = lambda: manager
    doc = a.list_documents()[0];change = dict(kind='set',glyph='A',layer='M1',field='width',before=600,after=608)
    request = patch(1);request.update(documentId=doc['id'],sourcePath=doc['path'],generation=doc['generation'],changes=[change])
    queue = QueueScheduler();core = BridgeCore(a,queue,chunk_limit=1)
    core.begin_apply(request);queue.run_one()
    assert manager.level == 1 and not manager.automatic and layer.width == 608
    if cancel:core.discard('job_1')
    queue.drain()
    assert manager.level == 0 and manager.automatic
    assert layer.width == (600 if cancel else 608)
    assert core.operation('job_1')['status'] == ('cancelled' if cancel else 'applied')
