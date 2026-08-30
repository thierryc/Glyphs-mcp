"""Runtime-owned Glyphs document lifecycle callbacks.

Callbacks deliberately resolve only the native document identity. Canonical
capture, file hashing, and history policy remain in the application layer.
"""

from __future__ import annotations

from typing import Any


def _font_from_notification(notification: Any) -> Any:
    try:
        value = notification.object() if hasattr(notification, "object") else notification
    except Exception:
        value = notification
    if value is None:
        return None
    font = getattr(value, "font", None)
    if callable(font):
        try:
            font = font()
        except Exception:
            font = None
    if font is not None:
        return font
    return value if getattr(value, "glyphs", None) is not None else None


class GlyphsDocumentLifecycleObserver:
    """Forward save/close notifications to the one active application."""

    def __init__(
        self,
        glyphs: Any,
        host: Any,
        application: Any,
        *,
        saved_event: Any,
        closed_event: Any,
    ) -> None:
        self._glyphs = glyphs
        self._host = host
        self._application = application
        self._callbacks: list[Any] = []
        for callback, event in (
            (self.document_was_saved_, saved_event),
            (self.document_was_closed_, closed_event),
        ):
            glyphs.addCallback(callback, event)
            self._callbacks.append(callback)

    @classmethod
    def install_from_running_glyphs(
        cls, host: Any, application: Any
    ) -> "GlyphsDocumentLifecycleObserver":
        from GlyphsApp import (  # type: ignore[import-not-found]
            DOCUMENTCLOSED,
            DOCUMENTWASSAVED,
            Glyphs,
        )

        return cls(
            Glyphs,
            host,
            application,
            saved_event=DOCUMENTWASSAVED,
            closed_event=DOCUMENTCLOSED,
        )

    def _document_id(self, notification: Any) -> str | None:
        font = _font_from_notification(notification)
        if font is None:
            return None
        try:
            return str(self._host.document_id_for_font(font) or "") or None
        except Exception:
            return None

    def document_was_saved_(self, notification: Any) -> None:
        font = _font_from_notification(notification)
        document_id = self._document_id(font)
        if document_id is None:
            return
        path_value = getattr(font, "filepath", None) if font is not None else None
        if callable(path_value):
            try:
                path_value = path_value()
            except Exception:
                path_value = None
        source_path = str(path_value) if path_value else None
        try:
            consume = getattr(
                self._host, "consume_save_notification_correlation", None
            )
            token = consume(document_id) if callable(consume) else None
            if token:
                try:
                    self._application.document_was_saved(
                        document_id,
                        correlation_token=str(token),
                        source_path=source_path,
                    )
                except TypeError:
                    self._application.document_was_saved(
                        document_id, correlation_token=str(token)
                    )
            else:
                try:
                    self._application.document_was_saved(
                        document_id, source_path=source_path
                    )
                except TypeError:
                    self._application.document_was_saved(document_id)
        except Exception:
            pass

    def document_was_closed_(self, notification: Any) -> None:
        document_id = self._document_id(notification)
        if document_id is None:
            return
        try:
            self._application.document_was_closed(document_id)
        except Exception:
            pass
        finally:
            clear = getattr(
                self._host, "clear_save_notification_correlation", None
            )
            if callable(clear):
                try:
                    clear(document_id)
                except Exception:
                    pass

    def close(self) -> None:
        for callback in self._callbacks:
            try:
                self._glyphs.removeCallback(callback)
            except Exception:
                pass
        self._callbacks = []


__all__ = ["GlyphsDocumentLifecycleObserver"]
