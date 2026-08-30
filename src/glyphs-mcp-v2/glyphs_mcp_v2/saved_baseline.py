"""Compatibility names for the unified saved-source service.

New code imports :mod:`glyphs_mcp_v2.saved_source`. These aliases keep the
initial Reporter-cache module importable for local extensions built against
the pre-optimization v2 candidate.
"""

from __future__ import annotations

from .saved_source import (
    SavedSourceSnapshot,
    SavedSourceStore,
    normalize_source_path,
    saved_source_signature,
)


SavedBaselineSnapshot = SavedSourceSnapshot
SavedBaselineCache = SavedSourceStore


__all__ = [
    "SavedBaselineCache",
    "SavedBaselineSnapshot",
    "normalize_source_path",
    "saved_source_signature",
]
