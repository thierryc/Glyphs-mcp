"""Explicit disposable-font gates to run inside Glyphs 3.5 and Glyphs 4."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from .adapters.document import (
    _save_font_copy,
    _serialized_font_fingerprint,
    native_font_to_model,
)
from .semantic import fingerprint_model


DISPOSABLE_FAMILY_PREFIX = "Glyphs MCP V2 Disposable"


def verify_copy_and_make_copy(font: Any, output_path: str) -> Mapping[str, Any]:
    """Verify clone/archive invariants without saving the working document."""

    family_name = str(getattr(font, "familyName", "") or "")
    if not family_name.startswith(DISPOSABLE_FAMILY_PREFIX):
        raise ValueError(
            "live v2 gates require a disposable font whose family name starts with {!r}".format(
                DISPOSABLE_FAMILY_PREFIX
            )
        )
    destination = Path(output_path)
    if not destination.is_absolute() or destination.exists():
        raise ValueError("the live-gate output must be a new explicit absolute path")
    if not destination.parent.is_dir():
        raise ValueError("the live-gate output parent must already exist")

    before_model = native_font_to_model(font)
    before_fingerprint = fingerprint_model(before_model)
    before_path = getattr(font, "filepath", None)
    document = getattr(font, "parent", None)
    before_dirty = getattr(document, "isDocumentEdited", None) if document is not None else None
    before_dirty = before_dirty() if callable(before_dirty) else before_dirty

    clone = font.copy()
    if clone is None or clone is font:
        raise AssertionError("GSFont.copy() did not return a detached clone")
    clone_fingerprint = fingerprint_model(native_font_to_model(clone))
    if clone_fingerprint != before_fingerprint:
        raise AssertionError("GSFont.copy() changed the canonical document model")
    if _serialized_font_fingerprint(clone) != _serialized_font_fingerprint(font):
        raise AssertionError("GSFont.copy() changed the serialized document archive")

    _save_font_copy(font, destination)
    os.chmod(destination, 0o600)

    after_path = getattr(font, "filepath", None)
    after_dirty = getattr(document, "isDocumentEdited", None) if document is not None else None
    after_dirty = after_dirty() if callable(after_dirty) else after_dirty
    after_fingerprint = fingerprint_model(native_font_to_model(font))
    if after_path != before_path or after_dirty != before_dirty:
        raise AssertionError("GSFont.save(makeCopy=True) changed the working path or dirty state")
    if after_fingerprint != before_fingerprint:
        raise AssertionError("the live working document changed during the copy gate")
    return {
        "familyName": family_name,
        "documentFingerprint": before_fingerprint,
        "copyFingerprint": clone_fingerprint,
        "outputPath": str(destination),
        "outputMode": "0600",
        "workingPathUnchanged": True,
        "dirtyStateUnchanged": True,
    }


__all__ = ["DISPOSABLE_FAMILY_PREFIX", "verify_copy_and_make_copy"]
