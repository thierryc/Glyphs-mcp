"""Glyphs 3.5/4 adapter for the read-only v2 application port."""

from __future__ import annotations

import platform
from threading import RLock
from typing import Any, Callable, Hashable, List, Optional, Sequence

from ..identity import DocumentIdRegistry
from ..ports import FontSnapshot, HostAccessError, HostRuntimeSnapshot, MainThreadExecutor
from .main_thread import GlyphsMainThreadExecutor


_MISSING_OBJC_ATTRIBUTES: set[tuple[type, str]] = set()
_MISSING_OBJC_ATTRIBUTES_LOCK = RLock()


def _is_objc_proxy(value: Any) -> bool:
    """Identify PyObjC instances without asking the proxy for more state."""

    try:
        metaclass_module = str(type(type(value)).__module__)
    except Exception:
        return False
    return metaclass_module == "objc" or metaclass_module.startswith("objc.")


def _maybe_call(value: Any) -> Any:
    if callable(value):
        try:
            return value()
        except Exception:
            return None
    return value


def _safe_getattr(value: Any, name: str, default: Any = None) -> Any:
    native_key = (type(value), str(name)) if _is_objc_proxy(value) else None
    if native_key is not None:
        with _MISSING_OBJC_ATTRIBUTES_LOCK:
            if native_key in _MISSING_OBJC_ATTRIBUTES:
                return default
    try:
        return getattr(value, name)
    except AttributeError:
        if native_key is not None:
            # PyObjC resolves an unknown selector by scanning the Objective-C
            # class and protocol metadata. Schema-v6 capture asks the same
            # official field of hundreds of same-class objects, so remember
            # the class-wide absence for the lifetime of this runtime.
            with _MISSING_OBJC_ATTRIBUTES_LOCK:
                _MISSING_OBJC_ATTRIBUTES.add(native_key)
        return default
    except Exception:
        return default


def _native_property(
    value: Any,
    name: str,
    default: Any = None,
    *,
    objc_boolean: bool = False,
) -> Any:
    """Read one Python or Objective-C property without leaking selectors.

    PyObjC does not expose every Objective-C Boolean property as a normal
    assignable Python attribute. A property declared with an ``isFoo`` getter
    can make ``object.foo`` resolve to a selector object instead of its value.
    Prefer the declared Boolean getter when requested, then normalize ordinary
    callable/property wrappers through the same path.
    """

    if objc_boolean:
        getter_name = "is{}{}".format(name[:1].upper(), name[1:])
        getter = _safe_getattr(value, getter_name)
        if getter is not None:
            resolved = _maybe_call(getter)
            if resolved is not None:
                return resolved
    resolved = _maybe_call(_safe_getattr(value, name, default))
    return default if resolved is None else resolved


def _set_native_property(value: Any, name: str, new_value: Any) -> None:
    """Write one Python or Objective-C property through its native contract.

    Prefer the explicit Objective-C ``setFoo:`` bridge when present. This
    avoids read-only or selector-shaped Python attributes while remaining
    compatible with plain Python fakes and older Glyphs wrappers.
    """

    setter_name = "set{}{}_".format(name[:1].upper(), name[1:])
    setter = _safe_getattr(value, setter_name)
    if callable(setter):
        setter(new_value)
        return
    setattr(value, name, new_value)


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
