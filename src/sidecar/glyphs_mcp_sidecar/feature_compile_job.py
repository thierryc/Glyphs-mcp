"""Saved-source OpenType compilation diagnostics for the external worker."""

from __future__ import annotations

from typing import Any

from glyphs_mcp_protocol.native_actions import state_hash

from .native_action_job import persistent_state
from .worker import WorkerError


def _value(owner: Any, name: str, default: Any = None) -> Any:
    try:
        result = getattr(owner, name)
        return result() if callable(result) else result
    except Exception:
        return default


def _error(value: Any, **context: Any) -> dict[str, Any]:
    if value is None:
        message = "OpenType feature compilation failed without a native diagnostic"
    elif isinstance(value, str):
        message = value
    else:
        message = _value(value, "localizedDescription", None) or str(value)
    result = {"message": str(message)}
    for source, target in (("domain", "domain"), ("code", "code")):
        item = _value(value, source, None) if value is not None else None
        if isinstance(item, (str, int)) and not isinstance(item, bool):
            result[target] = item
    result.update({key: item for key, item in context.items() if item is not None})
    return result


def _block_errors(font: Any) -> list[dict[str, Any]]:
    rows = []
    for block_type, collection_name in (
        ("prefix", "featurePrefixes"),
        ("class", "classes"),
        ("feature", "features"),
    ):
        for block in list(_value(font, collection_name, []) or []):
            identity = _value(block, "identifier", None) or _value(block, "id", None)
            name = _value(block, "name", None)
            raw_errors = _value(block, "errors", []) or []
            if isinstance(raw_errors, str):
                raw_errors = [raw_errors]
            try:
                errors = list(raw_errors)
            except Exception:
                errors = [raw_errors]
            for item in errors[:100]:
                rows.append(_error(
                    item,
                    blockType=block_type,
                    blockId=str(identity) if identity else None,
                    blockName=str(name) if name else None,
                ))
    return rows


def prepare(font: Any, request: dict[str, Any]) -> dict[str, Any]:
    if request.get("options", {}).get("mode") != "saved":
        raise WorkerError("the external compile worker accepts saved mode only")
    before_hash = state_hash(persistent_state(font, "font"))
    method = getattr(font, "compileFeatures", None)
    if not callable(method):
        raise WorkerError("Glyphs does not expose GSFont.compileFeatures()")
    outcome = method()
    if isinstance(outcome, tuple):
        success = outcome[0] is True
        native_error = outcome[1] if len(outcome) > 1 else None
    else:
        success = outcome is True
        native_error = None
    after_hash = state_hash(persistent_state(font, "font"))
    if before_hash != after_hash:
        raise WorkerError("feature compilation unexpectedly changed persisted feature source")
    errors = _block_errors(font)
    if not success and native_error is not None:
        native = _error(native_error)
        if native not in errors:
            errors.insert(0, native)
    if not success and not errors:
        errors.append(_error(None))
    return {
        "claim": "Saved-source OpenType compilation diagnostics",
        "success": success,
        "mode": "saved",
        "ephemeral": False,
        "beforeHash": before_hash,
        "afterHash": after_hash,
        "errors": errors,
        "warnings": [],
        "blockCount": sum(len(list(_value(font, name, []) or [])) for name in (
            "featurePrefixes", "classes", "features"
        )),
    }
