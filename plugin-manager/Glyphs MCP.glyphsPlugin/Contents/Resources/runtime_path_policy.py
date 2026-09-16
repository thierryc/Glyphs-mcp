#!/usr/bin/env python3
"""Shared dependency path policy for Glyphs MCP installers and runtime.

This module intentionally depends only on the Python standard library.  It is
loaded by the plug-in and by ``runtime_probe.py`` under the exact interpreter
selected in Glyphs, so both surfaces make the same path-ordering decision.
"""

from __future__ import annotations

import importlib
import os
import site
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


PATH_PLAN_SCHEMA_VERSION = 1
_SPECIAL_ORIGINS = {"built-in", "frozen", "namespace"}


def _logical(path: Path) -> Path:
    return Path(os.path.abspath(os.path.normpath(str(path))))


def _resolved(path: Path) -> Optional[Path]:
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return None


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _deduplicate_paths(paths: Sequence[Path]) -> List[Path]:
    result: List[Path] = []
    keys = set()
    for path in paths:
        logical = _logical(Path(path))
        resolved = _resolved(logical)
        key = str(resolved or logical)
        if key in keys:
            continue
        keys.add(key)
        result.append(logical)
    return result


def _is_embedded_glyphs_python(executable: Path) -> bool:
    resolved = _resolved(executable) or _logical(executable)
    return any(
        parent.name.lower().startswith("glyphs")
        and parent.name.lower().endswith(".app")
        for parent in resolved.parents
    )


def _user_site_packages() -> Optional[Path]:
    value = site.getusersitepackages()
    if isinstance(value, str) and value:
        return Path(value)
    return None


def build_runtime_path_plan(
    glyphs_site: Path,
    executable: Path = Path(sys.executable),
) -> Dict[str, Any]:
    """Return the dependency install and import policy for one interpreter."""
    glyphs_root = _logical(Path(glyphs_site))
    executable_path = _logical(Path(executable))
    embedded = _is_embedded_glyphs_python(executable_path)

    if embedded:
        primary = glyphs_root
        fallbacks: List[Path] = []
        install_mode = "target"
        runtime_kind = "embedded"
    else:
        user_root = _user_site_packages()
        if user_root is None:
            raise RuntimeError(
                "The selected Python interpreter did not provide a user site-packages path."
            )
        primary = _logical(user_root)
        fallbacks = [glyphs_root]
        install_mode = "user"
        runtime_kind = "external"

    ordered = _deduplicate_paths([primary, *fallbacks])
    primary = ordered[0]
    fallbacks = ordered[1:]
    return {
        "schemaVersion": PATH_PLAN_SCHEMA_VERSION,
        "runtimeKind": runtime_kind,
        "installMode": install_mode,
        "executable": str(executable_path),
        "primaryRoot": str(primary),
        "fallbackRoots": [str(path) for path in fallbacks],
        "orderedRoots": [str(path) for path in ordered],
    }


def _same_path(left: Path, right: Path) -> bool:
    left_logical = _logical(left)
    right_logical = _logical(right)
    if left_logical == right_logical:
        return True
    left_resolved = _resolved(left_logical)
    right_resolved = _resolved(right_logical)
    return (
        left_resolved is not None
        and right_resolved is not None
        and left_resolved == right_resolved
    )


def apply_runtime_path_plan(plan: Dict[str, Any]) -> List[str]:
    """Apply dependency roots at the first existing site-package position."""
    roots = _deduplicate_paths(
        [Path(value) for value in plan.get("orderedRoots", []) if value]
    )
    if not roots:
        raise ValueError("Runtime path plan has no ordered roots.")

    for root in roots:
        if root.is_dir():
            site.addsitedir(str(root))

    retained: List[str] = []
    insertion_index: Optional[int] = None
    for value in sys.path:
        if not value:
            retained.append(value)
            continue
        candidate = Path(value)
        if any(_same_path(candidate, root) for root in roots):
            if insertion_index is None:
                insertion_index = len(retained)
            continue
        if insertion_index is None and candidate.name in {
            "site-packages",
            "dist-packages",
        }:
            insertion_index = len(retained)
        retained.append(value)

    if insertion_index is None:
        insertion_index = len(retained)
    existing_roots = [str(root) for root in roots if root.is_dir()]
    retained[insertion_index:insertion_index] = existing_roots
    sys.path[:] = retained
    importlib.invalidate_caches()
    return existing_roots


def classify_origin(origin: str, plan: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Classify an import origin using logical and resolved containment."""
    if not origin or origin in _SPECIAL_ORIGINS:
        return {
            "status": "unexpected_origin",
            "logicalPath": origin or None,
            "resolvedPath": None,
            "logicalRoot": None,
            "resolvedRoot": None,
            "selectedRoot": None,
        }

    logical = _logical(Path(origin))
    resolved = _resolved(logical)
    roots = _deduplicate_paths(
        [Path(value) for value in plan.get("allowedRoots", plan.get("orderedRoots", [])) if value]
    )

    logical_root: Optional[Path] = None
    resolved_root: Optional[Path] = None
    for root in roots:
        if logical_root is None and _within(logical, root):
            logical_root = root
        root_resolved = _resolved(root)
        if (
            resolved_root is None
            and resolved is not None
            and root_resolved is not None
            and _within(resolved, root_resolved)
        ):
            resolved_root = root

    if resolved_root is not None:
        status = (
            "managed_origin"
            if logical_root == resolved_root
            else "symlink_to_allowed_origin"
        )
        # Import precedence is determined by the logical sys.path root even
        # when that root contains a package symlink into another allowed root.
        selected = logical_root or resolved_root
    elif logical_root is not None:
        status = "symlink_escape"
        selected = logical_root
    else:
        status = "unexpected_origin"
        selected = None

    return {
        "status": status,
        "logicalPath": str(logical),
        "resolvedPath": str(resolved) if resolved is not None else None,
        "logicalRoot": str(logical_root) if logical_root is not None else None,
        "resolvedRoot": str(resolved_root) if resolved_root is not None else None,
        "selectedRoot": str(selected) if selected is not None else None,
    }


__all__ = [
    "PATH_PLAN_SCHEMA_VERSION",
    "apply_runtime_path_plan",
    "build_runtime_path_plan",
    "classify_origin",
]
