"""Glyphs 3.5/4 adapter for the read-only v2 application port."""

from __future__ import annotations

import platform
from typing import Any, Callable, Hashable, List, Optional, Sequence

from ..identity import DocumentIdRegistry
from ..ports import FontSnapshot, HostAccessError, HostRuntimeSnapshot, MainThreadExecutor
from .main_thread import GlyphsMainThreadExecutor


def _maybe_call(value: Any) -> Any:
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _safe_getattr(value: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(value, name, default)
    except Exception:
        return default


def _sequence_values(value: Any) -> List[Any]:
    if value is None:
        return []
    try:
        return [value[index] for index in range(len(value))]
    except Exception:
        try:
            return list(value)
        except Exception:
            return []


def _safe_int(value: Any, default: int = 0, minimum: Optional[int] = None) -> int:
    try:
        result = int(_maybe_call(value))
    except Exception:
        result = int(default)
    if minimum is not None and result < minimum:
        return int(default)
    return result


def _safe_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(_maybe_call(value))
    except Exception:
        return None


def _native_unsaved_changes(document: Any) -> Optional[bool]:
    if document is None:
        return None
    # isDocumentEdited may be true solely because a Cocoa binding editor is
    # registered. hasUnautosavedChanges reflects document-content changes and
    # therefore matches the public v2 field's meaning more closely.
    for name in ("hasUnautosavedChanges", "isDocumentEdited"):
        value = _safe_getattr(document, name)
        if value is None:
            continue
        try:
            return bool(_maybe_call(value))
        except Exception:
            continue
    return None


class GlyphsHostAdapter:
    def __init__(
        self,
        app: Any,
        *,
        executor: Optional[MainThreadExecutor] = None,
        identities: Optional[DocumentIdRegistry] = None,
        native_identity: Optional[Callable[[Any], Hashable]] = None,
    ) -> None:
        if app is None:
            raise ValueError("app is required")
        self._app = app
        self._executor = executor or GlyphsMainThreadExecutor()
        self._identities = identities or DocumentIdRegistry()
        self._native_identity = native_identity or self._default_native_identity

    @classmethod
    def from_running_glyphs(cls) -> "GlyphsHostAdapter":
        try:
            from GlyphsApp import Glyphs  # type: ignore[import-not-found]
        except Exception as exc:
            raise HostAccessError("GlyphsApp is unavailable in this Python runtime.") from exc
        return cls(Glyphs)

    @staticmethod
    def _default_native_identity(value: Any) -> Hashable:
        try:
            import objc  # type: ignore[import-not-found]

            pyobjc_id = getattr(objc, "pyobjc_id", None)
            if callable(pyobjc_id):
                return ("native", int(pyobjc_id(value)))
        except Exception:
            pass
        return ("python", id(value))

    def _collect_fonts(self) -> Sequence[Any]:
        fonts: List[Any] = []
        seen: set[Hashable] = set()

        def add(font: Any) -> None:
            if font is None:
                return
            key = self._native_identity(font)
            if key in seen:
                return
            seen.add(key)
            fonts.append(font)

        for font in _sequence_values(_safe_getattr(self._app, "fonts")):
            add(font)
        for document in _sequence_values(_safe_getattr(self._app, "documents")):
            add(_maybe_call(_safe_getattr(document, "font")))
        current_document = _maybe_call(_safe_getattr(self._app, "currentDocument"))
        add(_maybe_call(_safe_getattr(current_document, "font")))
        add(_safe_getattr(self._app, "font"))
        return tuple(fonts)

    def _is_active(self, font: Any) -> bool:
        active = _safe_getattr(self._app, "font")
        if active is None:
            return False
        try:
            return self._native_identity(active) == self._native_identity(font)
        except Exception:
            return active is font

    def _font_snapshot(self, font: Any, legacy_index: int) -> FontSnapshot:
        native_key = self._native_identity(font)
        document_id = self._identities.resolve(native_key)
        file_path_value = _safe_getattr(font, "filepath")
        file_path = str(file_path_value) if file_path_value else None
        last_saved = _safe_getattr(font, "appVersion")
        document = _maybe_call(_safe_getattr(font, "parent"))
        has_unsaved_changes = _native_unsaved_changes(document)
        resolver = getattr(self, "resolve_verified_dirty_state", None)
        if callable(resolver):
            has_unsaved_changes = resolver(
                document_id, font, has_unsaved_changes
            )
        else:
            overrides = getattr(self, "_document_dirty_overrides", {})
            if document_id in overrides:
                has_unsaved_changes = overrides[document_id]
        return FontSnapshot(
            document_id=document_id,
            legacy_index=legacy_index,
            family_name=str(_safe_getattr(font, "familyName") or ""),
            file_path=file_path,
            has_unsaved_changes=has_unsaved_changes,
            active=self._is_active(font),
            master_count=len(_sequence_values(_safe_getattr(font, "masters"))),
            instance_count=len(_sequence_values(_safe_getattr(font, "instances"))),
            glyph_count=len(_sequence_values(_safe_getattr(font, "glyphs"))),
            units_per_em=_safe_int(_safe_getattr(font, "upm", 1000), 1000, minimum=1),
            version_major=_safe_int(_safe_getattr(font, "versionMajor", 0)),
            version_minor=_safe_int(_safe_getattr(font, "versionMinor", 0)),
            format_version=_safe_optional_int(_safe_getattr(font, "formatVersion")),
            last_saved_app_version=str(last_saved) if last_saved is not None else None,
        )

    def runtime_snapshot(self) -> HostRuntimeSnapshot:
        def capture() -> HostRuntimeSnapshot:
            fonts = self._collect_fonts()
            version = _safe_getattr(self._app, "versionString")
            if not version:
                version = _safe_getattr(self._app, "versionNumber")
            build = _safe_getattr(self._app, "buildNumber")
            return HostRuntimeSnapshot(
                application="Glyphs",
                application_version=str(_maybe_call(version) or "unknown"),
                build_number=str(_maybe_call(build) or "unknown"),
                python_version=platform.python_version(),
                open_document_count=len(fonts),
            )

        return self._executor.run(capture)

    def list_documents(self) -> Sequence[FontSnapshot]:
        def capture() -> Sequence[FontSnapshot]:
            return tuple(
                self._font_snapshot(font, index)
                for index, font in enumerate(self._collect_fonts())
            )

        return self._executor.run(capture)


__all__ = ["GlyphsHostAdapter"]
