"""Incremental release of existing operation resources; no new recovery state."""
import time


def finish(core, operation, status, error=None):
    if error is not None:
        operation["error"] = error.as_dict()
    operation["cleanupStatus"] = status
    if "cleanupSteps" in operation:
        return
    operation["cleanupSteps"] = operation_steps(core, operation)
    core._schedule(operation)


def operation_steps(core, operation):
    try:
        if operation.pop("undoOpen", False):
            name = "Glyphs MCP: " + operation["patch"]["summary"]
            steps = getattr(core.adapter, "end_undo_steps", None)
            if callable(steps):
                yield from steps(operation["documentId"], name)
            else:
                core.adapter.end_undo(operation["documentId"], name)
    except Exception as exc:
        record_error(core, operation, exc)
    # Drop wrapper references incrementally too. Native Undo owns its own
    # inverses, independently of these temporary rollback lists.
    while operation["applied"]:
        operation["applied"].pop()
        yield
    if operation["cleanupStatus"] != "applied":
        while operation["resolved"]:
            operation["resolved"].pop()
            yield
        operation["nativeStateBytes"] = 0


def record_error(core, operation, exc):
    operation["cleanupStatus"] = "failed"
    error = operation["error"] or core._error(exc).as_dict()
    error.setdefault("details", {})["cleanup"] = str(exc)
    operation["error"] = error


def run_chunk(core, operation, *, drain=False):
    deadline = time.perf_counter() + core.chunk_seconds
    processed = 0
    while drain or (processed < core.chunk_limit and time.perf_counter() < deadline):
        try:
            next(operation["cleanupSteps"])
        except StopIteration:
            with core._lock:
                operation.pop("cleanupSteps")
                operation.update(status=operation.pop("cleanupStatus"), finishedAt=time.time())
            return
        processed += 1
    core._schedule(operation)


def clear_adapter_steps(adapter, document_id):
    from .core import BridgeError
    states = adapter._rounding_states.get(document_id, {})
    failures = []
    while states:
        _, (layer, original) = states.popitem()
        try:
            restored = adapter._set_rounding(layer, original)
        except Exception:
            restored = False
        if not restored:
            try:
                identity = str(getattr(layer, "layerId", "unknown"))
            except Exception:
                identity = "unavailable layer"
            failures.append(identity)
        yield
    adapter._rounding_states.pop(document_id, None)
    layers = adapter._operation_layers.get(document_id, {})
    while layers:
        layers.popitem()
        yield
    adapter._operation_layers.pop(document_id, None)
    adapter._operation_fonts.pop(document_id, None)
    if failures:
        raise BridgeError("native_write_failed", "Could not restore rounding flags", details={"layers": failures})
