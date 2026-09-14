"""Shared dependency path policy for the Glyphs MCP runtime and installers.

This module is intentionally standard-library-only.  It is copied unchanged
into every distributable plug-in bundle and is executed by the exact Python
interpreter selected for Glyphs.
"""

from __future__ import annotations

import os
import site
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional


SCHEMA_VERSION = 1


def _resolved(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser().absolute()


def _is_within(path: Path, root: Path, *, resolve: bool) -> bool:
    candidate = _resolved(path) if resolve else path.expanduser().absolute()
    boundary = _resolved(root) if resolve else root.expanduser().absolute()
    try:
        candidate.relative_to(boundary)
        return True
    except ValueError:
        return False


def _deduplicate(paths: Iterable[Path]) -> List[Path]:
    result: List[Path] = []
    identities = set()
    for path in paths:
        identity = os.path.normcase(str(_resolved(path)))
        if identity in identities:
            continue
        identities.add(identity)
        result.append(path.expanduser().absolute())
    return result


def _is_embedded_glyphs_python(executable: Path) -> bool:
    resolved = _resolved(executable)
    return any(
        parent.name.lower().startswith("glyphs") and parent.suffix.lower() == ".app"
        for parent in resolved.parents
    )


def build_runtime_path_plan(
    glyphs_site: os.PathLike[str] | str,
    executable: os.PathLike[str] | str = sys.executable,
    *,
    user_site: Optional[os.PathLike[str] | str] = None,
) -> Dict[str, Any]:
    """Return the serializable path plan for *executable* and *glyphs_site*."""
    executable_path = _resolved(Path(executable))
    glyphs_path = Path(glyphs_site).expanduser().absolute()
    embedded = _is_embedded_glyphs_python(executable_path)
    if embedded:
        roots = [glyphs_path]
        install_mode = "target"
    else:
        if user_site is None:
            discovered = site.getusersitepackages()
            if isinstance(discovered, (list, tuple)):
                discovered = discovered[0] if discovered else ""
            user_site = discovered
        user_path = Path(user_site).expanduser().absolute() if user_site else None
        roots = [path for path in (user_path, glyphs_path) if path is not None]
        install_mode = "user"
    ordered = _deduplicate(roots)
    primary = ordered[0]
    return {
        "schemaVersion": SCHEMA_VERSION,
        "runtimeKind": "embedded" if embedded else "external",
        "installMode": install_mode,
        "executable": str(executable_path),
        "primaryRoot": str(primary),
        "fallbackRoots": [str(path) for path in ordered[1:]],
        "orderedRoots": [str(path) for path in ordered],
    }


def _first_site_packages_index(entries: List[str]) -> int:
    for index, entry in enumerate(entries):
        if entry and Path(entry).name == "site-packages":
            return index
    return len(entries)


def apply_runtime_path_plan(
    plan: Mapping[str, Any], *, path_entries: Optional[List[str]] = None
) -> List[str]:
    """Apply managed roots at the first site-packages position, in plan order."""
    target = sys.path if path_entries is None else path_entries
    ordered = [Path(value) for value in plan.get("orderedRoots", []) if value]
    identities = {os.path.normcase(str(_resolved(path))) for path in ordered}
    retained: List[str] = []
    for entry in target:
        if not entry:
            retained.append(entry)
            continue
        identity = os.path.normcase(str(_resolved(Path(entry))))
        if identity not in identities:
            retained.append(entry)
    insertion = _first_site_packages_index(retained)
    additions: List[str] = []
    for root in ordered:
        if not root.is_dir():
            continue
        introduced: List[str] = []
        if target is sys.path:
            before = list(target)
            try:
                site.addsitedir(str(root))
            except OSError:
                pass
            # Retain any paths introduced by .pth files immediately after their
            # owning root without disturbing resources, vendored deps, or stdlib.
            introduced = [
                entry for entry in target if entry not in before and entry != str(root)
            ]
        additions.extend([str(root), *introduced])
    target[:] = retained[:insertion] + additions + retained[insertion:]
    return target


def classify_origin(origin: os.PathLike[str] | str, plan: Mapping[str, Any]) -> Dict[str, Any]:
    """Classify a logical package origin and its resolved symlink target."""
    logical = Path(origin).expanduser().absolute()
    resolved = _resolved(logical)
    roots = [Path(value) for value in plan.get("orderedRoots", [])]
    logical_root = next((root for root in roots if _is_within(logical, root, resolve=False)), None)
    resolved_root = next((root for root in roots if _is_within(resolved, root, resolve=True)), None)
    if logical_root is not None and resolved_root is None:
        code, accepted, blocking = "symlink_escape", False, True
    elif logical_root is None and resolved_root is None:
        code, accepted, blocking = "unexpected_origin", False, True
    else:
        code, accepted, blocking = "accepted", True, False
    selected = logical_root or resolved_root
    return {
        "code": code,
        "accepted": accepted,
        "blocking": blocking,
        "logicalOrigin": str(logical),
        "resolvedOrigin": str(resolved),
        "selectedRoot": str(selected) if selected else None,
    }


__all__ = [
    "SCHEMA_VERSION",
    "apply_runtime_path_plan",
    "build_runtime_path_plan",
    "classify_origin",
]
