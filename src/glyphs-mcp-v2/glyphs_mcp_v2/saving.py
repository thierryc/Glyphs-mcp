"""Typed errors and constants for verified native document saves."""

from __future__ import annotations

from typing import Any, Mapping, Optional


SAVE_OVERWRITE_POLICIES = ("fail_if_exists", "replace_if_match")
SAVE_SOURCE_KINDS = ("glyphs", "glyphspackage")


class DocumentSaveError(RuntimeError):
    """A bounded save failure that the application can publish verbatim."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        recoverable: bool = True,
        details: Optional[Mapping[str, Any]] = None,
        write_attempted: bool = False,
    ) -> None:
        super().__init__(str(message))
        self.code = str(code)
        self.message = str(message)
        self.recoverable = bool(recoverable)
        self.details = dict(details or {})
        self.write_attempted = bool(write_attempted)


__all__ = [
    "DocumentSaveError",
    "SAVE_OVERWRITE_POLICIES",
    "SAVE_SOURCE_KINDS",
]
