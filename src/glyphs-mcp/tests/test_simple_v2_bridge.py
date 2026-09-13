"""Time-sliced bridge lifecycle tests without Glyphs or AppKit."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


REPO = Path(__file__).resolve().parents[3]
for root in (REPO / "src" / "protocol", REPO / "src" / "bridge"):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from glyphs_mcp_bridge.core import BridgeCore, BridgeError  # noqa: E402
from glyphs_mcp_bridge.main_thread import CocoaMainThread  # noqa: E402


class QueueScheduler:
    def __init__(self) -> None:
        self.items = []
        self.calls = 0

    def __call__(self, callback) -> None:
        self.items.append(callback)
        self.calls += 1

    def run_one(self) -> None:
        self.items.pop(0)()

    def drain(self) -> None:
        while self.items:
            self.run_one()


class FakeAdapter:
    def __init__(self, count: int = 1) -> None:
        self.path = "/tmp/Test.glyphs"
        self.dirty = False
        self.generation = 7
        self.values = {("g" + str(index), "M1", "width"): 600 for index in range(count)}
        self.undo = []
        self.writes = []

    def list_documents(self):
        return [self.document_state("doc_1")]

    def read_entities(self, document_id, entities, fields):
        return [{"entity": item, "values": {field: "value" for field in fields}} for item in entities]

    def document_state(self, document_id):
        assert document_id == "doc_1"
        return {
            "id": "doc_1",
            "path": self.path,
            "dirty": self.dirty,
            "generation": self.generation,
        }

    def current_value(self, document_id, change, *, reverse=False):
        return self.values[(change["glyph"], change["layer"], change["field"])]

    def apply_change(self, document_id, change, *, reverse=False):
        self.writes.append((change["glyph"], reverse))
        self.values[(change["glyph"], change["layer"], change["field"])] = (
            change["before"] if reverse else change["after"]
        )

    def begin_undo(self, document_id):
        self.undo.append(("begin", document_id))

    def end_undo(self, document_id, name):
        self.undo.append(("end", document_id, name))


def patch(count: int) -> dict[str, Any]:
    return {
        "version": 1,
        "jobId": "job_1",
        "documentId": "doc_1",
        "sourcePath": "/tmp/Test.glyphs",
        "sourceHash": "sha256:" + "a" * 64,
        "generation": 7,
        "changes": [
            {
                "kind": "set",
                "glyph": "g" + str(index),
                "layer": "M1",
                "field": "width",
                "before": 600,
                "after": 608,
            }
            for index in range(count)
        ],
        "summary": "Add 8 units to all layers",
    }


def test_large_patch_yields_and_has_one_human_acceptance() -> None:
    adapter = FakeAdapter(121)
    scheduler = QueueScheduler()
    core = BridgeCore(adapter, scheduler, chunk_ms=10, chunk_limit=50)
    started = core.begin_apply(patch(121))
    assert started["status"] == "applying"
    assert scheduler.calls == 1
    scheduler.run_one()
    assert core.operation("job_1")["completedChanges"] == 50
    assert scheduler.items
    scheduler.drain()
    completed = core.operation("job_1")
    assert completed["status"] == "applied"
    assert "Save to accept" in completed["message"]
    assert "approval" not in completed["message"].lower()
    assert set(adapter.values.values()) == {608}
    assert len([item for item in adapter.undo if item[0] == "begin"]) == 1
    assert len([item for item in adapter.undo if item[0] == "end"]) == 1
    assert scheduler.calls >= 3


def test_conflict_rolls_back_already_written_targets() -> None:
    adapter = FakeAdapter(80)
    scheduler = QueueScheduler()
    core = BridgeCore(adapter, scheduler, chunk_limit=20)
    core.begin_apply(patch(80))
    scheduler.run_one()
    adapter.values[("g25", "M1", "width")] = 777
    scheduler.drain()
    result = core.operation("job_1")
    assert result["status"] == "failed"
    assert result["error"]["code"] == "target_conflict"
    assert all(
        value == (777 if key[0] == "g25" else 600)
        for key, value in adapter.values.items()
    )


def test_discard_reverses_only_still_current_targets() -> None:
    adapter = FakeAdapter(12)
    scheduler = QueueScheduler()
    core = BridgeCore(adapter, scheduler, chunk_limit=5)
    core.begin_apply(patch(12))
    scheduler.drain()
    assert core.discard("job_1")["status"] == "discarding"
    scheduler.drain()
    assert core.operation("job_1")["status"] == "discarded"
    assert set(adapter.values.values()) == {600}
    assert adapter.writes[-12:] == [("g" + str(index), True) for index in range(12)]


def test_small_native_scalar_normalization_preserves_relative_change_and_discard() -> None:
    adapter = FakeAdapter()
    adapter.values[("g0", "M1", "width")] = 1070.0
    scheduler = QueueScheduler()
    core = BridgeCore(adapter, scheduler)
    value = patch(1)
    value["changes"][0]["before"] = 1070.01
    value["changes"][0]["after"] = 1078.01

    core.begin_apply(value)
    scheduler.drain()
    assert core.operation("job_1")["status"] == "applied"
    assert adapter.values[("g0", "M1", "width")] == 1078.0

    core.discard("job_1")
    scheduler.drain()
    assert core.operation("job_1")["status"] == "discarded"
    assert adapter.values[("g0", "M1", "width")] == 1070.0


def test_native_scalar_difference_beyond_normalization_tolerance_fails_closed() -> None:
    adapter = FakeAdapter()
    adapter.values[("g0", "M1", "width")] = 1069.0
    scheduler = QueueScheduler()
    core = BridgeCore(adapter, scheduler)
    value = patch(1)
    value["changes"][0]["before"] = 1070.01
    value["changes"][0]["after"] = 1078.01

    core.begin_apply(value)
    scheduler.drain()
    result = core.operation("job_1")
    assert result["status"] == "failed"
    assert result["error"]["code"] == "target_conflict"
    assert result["error"]["details"]["observed"] == 1069.0


def test_dirty_or_stale_document_fails_before_undo_or_write() -> None:
    adapter = FakeAdapter()
    scheduler = QueueScheduler()
    core = BridgeCore(adapter, scheduler)
    adapter.dirty = True
    with pytest.raises(BridgeError) as caught:
        core.begin_apply(patch(1))
    assert caught.value.code == "document_not_clean"
    assert not adapter.undo
    adapter.dirty = False
    adapter.generation = 8
    with pytest.raises(BridgeError) as caught:
        core.begin_apply(patch(1))
    assert caught.value.code == "stale_document"
    assert not adapter.undo


def test_reads_are_explicitly_bounded() -> None:
    adapter = FakeAdapter()
    core = BridgeCore(adapter, QueueScheduler())
    with pytest.raises(BridgeError, match="1-100"):
        core.read_entities("doc_1", [{"kind": "glyph", "id": "A"}] * 101, ["name"])


def test_cocoa_scheduler_yields_to_the_application_run_loop(monkeypatch) -> None:
    scheduled = []
    helper = SimpleNamespace(
        callLater=lambda delay, callback: scheduled.append((delay, callback))
    )
    monkeypatch.setitem(sys.modules, "PyObjCTools", SimpleNamespace(AppHelper=helper))
    callback = lambda: None

    main = CocoaMainThread(yield_seconds=0.002)
    main.schedule(callback)

    assert scheduled == [(0.002, callback)]


def test_same_document_cannot_start_overlapping_native_undo_groups():
    adapter = FakeAdapter(100)
    scheduler = QueueScheduler()
    core = BridgeCore(adapter, scheduler)
    core.begin_apply(patch(100))
    other = patch(100)
    other['jobId'] = 'job_other'
    with pytest.raises(BridgeError, match='another operation'):
        core.begin_apply(other)
    assert len(adapter.undo) == 1
    scheduler.drain()


def test_completed_operation_retention_is_bounded():
    adapter = FakeAdapter()
    scheduler = QueueScheduler()
    core = BridgeCore(adapter, scheduler)
    for index in range(20):
        value = patch(1)
        value['jobId'] = 'job_' + str(index)
        core.begin_apply(value)
        scheduler.drain()
        core.discard(value['jobId'])
        scheduler.drain()
    assert len(core._operations) == 8
    assert all(not item['resolved'] and not item['applied'] for item in core._operations.values())
    assert core.operation('job_19')['status'] == 'discarded'


def test_discard_cannot_steal_document_from_another_operation():
    adapter, queue = FakeAdapter(), QueueScheduler()
    core = BridgeCore(adapter, queue)
    core.begin_apply(patch(1))
    queue.drain()
    other = patch(1)
    other['jobId'] = 'job_other'
    other['changes'][0].update(before=608, after=616)
    core.begin_apply(other)
    before = core.operation('job_1'), list(adapter.undo), list(adapter.writes)
    with pytest.raises(BridgeError, match='another operation'):
        core.discard('job_1')
    assert (core.operation('job_1'), adapter.undo, adapter.writes) == before
    assert core.status()['activeOperations'] == 1
    queue.drain()


def test_repeated_discard_is_idempotent():
    adapter, queue = FakeAdapter(), QueueScheduler()
    core = BridgeCore(adapter, queue)
    core.begin_apply(patch(1))
    queue.drain()
    first = core.discard('job_1')
    assert core.discard('job_1') == first
    assert len(queue.items) == 1
    assert len(adapter.undo) == 3
    queue.drain()


def test_ownership_is_reserved_before_native_undo_can_reenter():
    adapter, queue = FakeAdapter(), QueueScheduler()
    core = BridgeCore(adapter, queue)
    original = adapter.begin_undo
    other = patch(1)
    other['jobId'] = 'job_other'

    def begin(document_id):
        adapter.begin_undo = original
        assert core.begin_apply(patch(1))['status'] == 'applying'
        with pytest.raises(BridgeError, match='another operation'):
            core.begin_apply(other)
        original(document_id)

    adapter.begin_undo = begin
    core.begin_apply(patch(1))
    queue.drain()
    assert len(adapter.undo) == 2


@pytest.mark.parametrize('failure', ['begin', 'schedule', 'end'])
def test_failed_native_scope_releases_document_and_keeps_terminal_record(failure):
    adapter, queue = FakeAdapter(), QueueScheduler()
    core = BridgeCore(adapter, queue)

    def fail(*args):
        raise RuntimeError('scope failure')

    if failure == 'begin':
        adapter.begin_undo = fail
    elif failure == 'schedule':
        core.schedule = fail
    else:
        adapter.end_undo = fail
    core.begin_apply(patch(1))
    queue.drain()
    assert core.operation('job_1')['status'] == 'failed'
    assert core.status()['activeOperations'] == 0
    assert core.begin_apply(patch(1))['status'] == 'failed'


@pytest.mark.parametrize('failure', ['setter', 'readback', 'mismatch', 'recovery'])
def test_current_target_recovers_before_yield_then_earlier_targets_roll_back(failure):
    class PartialAdapter(FakeAdapter):
        failed = False
        def apply_change(self, doc, change, *, reverse=False):
            if reverse and change['glyph'] == 'g1' and failure == 'recovery':
                raise RuntimeError('recovery setter failed')
            super().apply_change(doc, change, reverse=reverse)
            if change['glyph'] == 'g1' and not reverse:
                if failure in {'setter', 'recovery'}:
                    raise RuntimeError('setter failed after mutation')
                if failure == 'mismatch':
                    self.values[('g1', 'M1', 'width')] = 607
        def current_value(self, doc, change, *, reverse=False):
            if (failure == 'readback' and change['glyph'] == 'g1'
                    and self.values[('g1', 'M1', 'width')] == 608 and not self.failed):
                self.failed = True
                raise RuntimeError('readback unavailable')
            return super().current_value(doc, change, reverse=reverse)

    adapter, queue = PartialAdapter(3), QueueScheduler()
    core = BridgeCore(adapter, queue, chunk_limit=1)
    core.begin_apply(patch(3))
    queue.run_one()
    queue.run_one()
    assert adapter.values[('g1', 'M1', 'width')] == (608 if failure == 'recovery' else 600)
    assert adapter.values[('g0', 'M1', 'width')] == 608
    queue.drain()
    result = core.operation('job_1')
    assert result['status'] == 'failed'
    assert adapter.values[('g0', 'M1', 'width')] == 600
    assert adapter.values[('g2', 'M1', 'width')] == 600
    assert result['error']['details']['recovery']['complete'] is (failure != 'recovery')


def test_conflict_during_rollback_is_preserved_and_recovery_is_explicitly_incomplete():
    adapter, queue = FakeAdapter(3), QueueScheduler()
    core = BridgeCore(adapter, queue, chunk_limit=1)
    core.begin_apply(patch(3))
    queue.run_one()
    adapter.values[('g1', 'M1', 'width')] = 777
    queue.run_one()
    adapter.values[('g0', 'M1', 'width')] = 888
    queue.drain()
    result = core.operation('job_1')
    assert result['error']['code'] == 'target_conflict'
    assert result['error']['details']['recovery'] == {'complete': False, 'remaining': 1}
    assert adapter.values[('g0', 'M1', 'width')] == 888
