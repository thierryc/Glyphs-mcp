"""One-shot synchronous NSDocument save adapter."""

from __future__ import annotations

from typing import Any


def _call(value: Any) -> Any:
    return value() if callable(value) else value


def _value(owner: Any, name: str, default: Any = None) -> Any:
    try:
        return _call(getattr(owner, name))
    except Exception:
        return default


def _native_error(result: Any) -> str | None:
    success = result
    error = None
    if isinstance(result, tuple):
        success = result[0] if result else False
        error = result[1] if len(result) > 1 else None
    if bool(success) and error is None:
        return None
    for name in (
        "localizedRecoverySuggestion",
        "localizedFailureReason",
        "localizedDescription",
    ):
        value = _value(error, name, None) if error is not None else None
        if value:
            return str(value)[:2048]
    return "Glyphs reported that the native document save failed."


def save_document(adapter, document_id: str, target: str, mode: str, error_type):
    font = adapter._font(document_id)
    document = _value(font, "parent", None)
    selector = getattr(document, "saveToURL_ofType_forSaveOperation_error_", None)
    if not callable(selector):
        raise error_type(
            "native_save_failed",
            "Glyphs did not expose the synchronous NSDocument save selector",
            details={"writeAttempted": False},
        )
    try:
        from Foundation import NSURL  # type: ignore[import-not-found]
        try:
            from AppKit import NSSaveAsOperation, NSSaveOperation  # type: ignore[import-not-found]
        except Exception:
            NSSaveOperation = 0
            NSSaveAsOperation = 1
    except Exception as exc:
        raise error_type(
            "native_save_failed",
            "Glyphs native save constants are unavailable",
            details={"writeAttempted": False, "exceptionType": type(exc).__name__},
        ) from exc

    type_name = (
        "com.glyphsapp.glyphspackage"
        if str(target).lower().endswith(".glyphspackage")
        else "com.schriftgestaltung.glyphs"
    )
    operation = NSSaveOperation if mode == "save" else NSSaveAsOperation
    try:
        result = selector(
            NSURL.fileURLWithPath_(str(target)), type_name, operation, None
        )
        native_error = _native_error(result)
        state = adapter._document_state(font)
    except Exception as exc:
        try:
            state = adapter._document_state(font)
        except Exception:
            state = {}
        raise error_type(
            "save_verification_failed",
            "Glyphs raised while performing the native document save",
            details={
                "writeAttempted": True,
                "nativeSaveSucceeded": False,
                "exceptionType": type(exc).__name__,
                "path": state.get("path"),
                "dirty": state.get("dirty"),
            },
        ) from exc
    return {
        "writeAttempted": True,
        "nativeSaveSucceeded": native_error is None,
        "nativeError": native_error,
        "path": state.get("path"),
        "dirty": state.get("dirty"),
        "generation": state.get("generation"),
    }
