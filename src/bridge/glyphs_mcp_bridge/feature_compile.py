"""Qualified live-editor OpenType compilation with persisted-state guards."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from glyphs_mcp_protocol.native_actions import state_hash

from . import native_actions


def _value(owner: Any, name: str, default: Any = None) -> Any:
    try:
        result = getattr(owner, name)
        return result() if callable(result) else result
    except Exception:
        return default


def _error(value: Any, **context: Any) -> dict[str, Any]:
    message = (
        "OpenType feature compilation failed without a native diagnostic"
        if value is None
        else value if isinstance(value, str)
        else _value(value, "localizedDescription", None) or str(value)
    )
    result = {"message": str(message)}
    for name in ("domain", "code"):
        item = _value(value, name, None) if value is not None else None
        if isinstance(item, (str, int)) and not isinstance(item, bool):
            result[name] = item
    result.update({key: item for key, item in context.items() if item is not None})
    return result


def _block_errors(font: Any) -> list[dict[str, Any]]:
    result = []
    for block_type, collection_name in (
        ("prefix", "featurePrefixes"), ("class", "classes"), ("feature", "features")
    ):
        for block in list(_value(font, collection_name, []) or []):
            raw = _value(block, "errors", []) or []
            if isinstance(raw, str):
                raw = [raw]
            try:
                errors = list(raw)
            except Exception:
                errors = [raw]
            identity = _value(block, "identifier", None) or _value(block, "id", None)
            name = _value(block, "name", None)
            for item in errors[:100]:
                result.append(_error(
                    item,
                    blockType=block_type,
                    blockId=str(identity) if identity else None,
                    blockName=str(name) if name else None,
                ))
    return result


@lru_cache(maxsize=1)
def available() -> bool:
    try:
        from GlyphsApp import GSFont  # type: ignore[import-not-found]

        candidate = GSFont.alloc().init()
        if not callable(getattr(candidate, "compileFeatures", None)):
            return False
        before = native_actions.current_hash(candidate, "font")
        snapshot = native_actions.capture(candidate, "font")
        native_actions.restore(candidate, snapshot)
        return native_actions.current_hash(candidate, "font") == before
    except Exception:
        return False


def compile(font: Any) -> dict[str, Any]:
    before_hash = state_hash(native_actions.persistent_state(font, "font"))
    snapshot = native_actions.capture(font, "font")
    method = getattr(font, "compileFeatures", None)
    if not callable(method):
        raise ValueError("Glyphs does not expose GSFont.compileFeatures()")
    try:
        outcome = method()
        if isinstance(outcome, tuple):
            success = outcome[0] is True
            native_error = outcome[1] if len(outcome) > 1 else None
        else:
            success = outcome is True
            native_error = None
        after_hash = state_hash(native_actions.persistent_state(font, "font"))
        if before_hash != after_hash:
            native_actions.restore(font, snapshot)
            restored = state_hash(native_actions.persistent_state(font, "font"))
            if restored != before_hash:
                raise ValueError("live feature compilation changed persisted source and restoration failed")
            raise ValueError("live feature compilation unexpectedly changed persisted feature source")
    except Exception:
        observed = state_hash(native_actions.persistent_state(font, "font"))
        if observed != before_hash:
            native_actions.restore(font, snapshot)
        raise
    errors = _block_errors(font)
    if not success and native_error is not None:
        native = _error(native_error)
        if native not in errors:
            errors.insert(0, native)
    if not success and not errors:
        errors.append(_error(None))
    return {
        "claim": "Live-editor OpenType compilation diagnostics",
        "success": success,
        "mode": "live",
        "ephemeral": True,
        "beforeHash": before_hash,
        "afterHash": before_hash,
        "errors": errors,
        "warnings": [],
        "blockCount": sum(len(list(_value(font, name, []) or [])) for name in (
            "featurePrefixes", "classes", "features"
        )),
    }
