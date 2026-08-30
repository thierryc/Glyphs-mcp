"""Single-source contract for detached Glyphs MCP Python execution."""

from __future__ import annotations

import builtins
import hashlib
import json
import sys
from typing import Any, Iterable, Mapping


DETACHED_PYTHON_CONTRACT_VERSION = 1
DETACHED_PYTHON_BASELINE = (3, 14)
DETACHED_PYTHON_MODES = ("read_only", "staged_document")
PYTHON_MODES = DETACHED_PYTHON_MODES + ("live_open_world",)

ALLOWED_IMPORT_ROOTS = frozenset(
    {"functools", "itertools", "json", "math", "re", "statistics"}
)
DANGEROUS_IMPORT_ROOTS = frozenset(
    {
        "AppKit",
        "Foundation",
        "GlyphsApp",
        "PyObjCTools",
        "http",
        "objc",
        "os",
        "pathlib",
        "requests",
        "shutil",
        "socket",
        "subprocess",
        "sys",
        "tempfile",
        "urllib",
    }
)
HOST_EFFECT_METHOD_NAMES = frozenset(
    {"close", "popen", "remove", "save", "show", "system", "unlink", "write"}
)
INTERNAL_BUILTIN_NAMES = frozenset({"__build_class__", "__import__"})
INTERNAL_GLOBALS = {
    "__doc__": None,
    "__loader__": None,
    "__name__": "__glyphs_mcp_detached__",
    "__package__": None,
    "__spec__": None,
}
DENIED_BUILTIN_GROUPS = {
    "dynamicCode": ("compile", "eval", "exec"),
    "externalEffects": ("breakpoint", "input", "open"),
    "interactiveHelpers": (
        "copyright",
        "credits",
        "exit",
        "help",
        "license",
        "quit",
    ),
    "processControlExceptions": (
        "GeneratorExit",
        "KeyboardInterrupt",
        "SystemExit",
    ),
    "internalImportHook": ("__import__",),
}
DENIED_BUILTIN_NAMES = frozenset(
    name for names in DENIED_BUILTIN_GROUPS.values() for name in names
)
POLICY_FORBIDDEN_CALL_NAMES = frozenset(
    set(DENIED_BUILTIN_GROUPS["dynamicCode"])
    | set(DENIED_BUILTIN_GROUPS["externalEffects"])
    | set(DENIED_BUILTIN_GROUPS["internalImportHook"])
    | {"exit", "quit"}
)
CONTEXT_FIELDS = {
    "font": {"nullable": False, "description": "Detached GSFont clone."},
    "glyph": {"nullable": True, "description": "Requested glyph, when scoped."},
    "master": {"nullable": True, "description": "Requested master, when scoped."},
    "layer": {"nullable": True, "description": "Requested layer, when scoped."},
    "selectedLayers": {
        "nullable": False,
        "description": "Requested layer as a bounded list, or an empty list.",
    },
}
NATIVE_CONSTRUCTOR_NAMES = (
    "GSClass",
    "GSFeature",
    "GSFeaturePrefix",
    "GSFontMaster",
    "GSGlyph",
    "GSInstance",
    "GSLayer",
    "MGOrderedDictionary",
)

# Public/non-private built-ins plus the two hooks required by Python syntax.
# Any Python 3.14 built-in drift must be reviewed before the deployed namespace
# can change silently.
PYTHON_314_BUILTIN_SNAPSHOT_COUNT = 152
PYTHON_314_BUILTIN_SNAPSHOT_FINGERPRINT = (
    "sha256:d877989fe2e7c4937622221cf8daaba9f22b37c7799aa75797df50bc54470b5c"
)


class StagedImportUnavailable(ImportError):
    """A detached script requested an import outside the advertised roots."""

    def __init__(self, requested_import: str) -> None:
        self.requested_import = str(requested_import or "")
        self.import_root = self.requested_import.split(".", 1)[0]
        super().__init__(
            "detached Python cannot import {}".format(
                self.requested_import or "a relative module"
            )
        )


def _sha_json(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _reviewed_builtin_names() -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name in vars(builtins)
            if not name.startswith("_") or name in INTERNAL_BUILTIN_NAMES
        )
    )


def builtin_snapshot() -> dict[str, Any]:
    names = _reviewed_builtin_names()
    fingerprint = _sha_json(list(names))
    supported_minor = sys.version_info[:2] == DETACHED_PYTHON_BASELINE
    reviewed = bool(
        supported_minor
        and len(names) == PYTHON_314_BUILTIN_SNAPSHOT_COUNT
        and fingerprint == PYTHON_314_BUILTIN_SNAPSHOT_FINGERPRINT
    )
    return {
        "baselinePython": "{}.{}".format(*DETACHED_PYTHON_BASELINE),
        "runtimePython": "{}.{}.{}".format(*sys.version_info[:3]),
        "nameCount": len(names),
        "fingerprint": fingerprint,
        "reviewed": reviewed,
        "supportedMinor": supported_minor,
    }


def require_reviewed_builtin_snapshot() -> None:
    snapshot = builtin_snapshot()
    if sys.version_info[:2] > DETACHED_PYTHON_BASELINE:
        raise RuntimeError(
            "Python {}.{} is newer than the reviewed detached Python contract".format(
                *sys.version_info[:2]
            )
        )
    if snapshot["supportedMinor"] and not snapshot["reviewed"]:
        raise RuntimeError(
            "Python 3.14 built-ins changed; review the detached Python contract"
        )


def _safe_import(
    name: str,
    globals_value: Any = None,
    locals_value: Any = None,
    fromlist: Any = (),
    level: int = 0,
) -> Any:
    root = str(name or "").split(".", 1)[0]
    if level or root not in ALLOWED_IMPORT_ROOTS:
        raise StagedImportUnavailable(str(name or ""))
    return builtins.__import__(name, globals_value, locals_value, fromlist, level)


def detached_builtins() -> dict[str, Any]:
    """Return the effective near-standard namespace for a detached script."""

    require_reviewed_builtin_snapshot()
    namespace = {
        name: value
        for name, value in vars(builtins).items()
        if (not name.startswith("_") or name in INTERNAL_BUILTIN_NAMES)
        and name not in DENIED_BUILTIN_NAMES
    }
    namespace["__build_class__"] = builtins.__build_class__
    namespace["__import__"] = _safe_import
    return namespace


def public_builtin_names() -> tuple[str, ...]:
    return tuple(
        sorted(set(detached_builtins()) - set(INTERNAL_BUILTIN_NAMES))
    )


def unavailable_standard_builtin_names() -> frozenset[str]:
    return frozenset(
        name
        for name in DENIED_BUILTIN_NAMES
        if name in vars(builtins) and name not in INTERNAL_BUILTIN_NAMES
    )


def build_detached_namespace(
    context: Mapping[str, Any],
    *,
    constructors: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    missing = sorted(set(CONTEXT_FIELDS) - set(context))
    if missing:
        raise ValueError(
            "detached Python context omitted {}".format(", ".join(missing))
        )
    resolved_constructors = dict(constructors or {})
    unsupported = sorted(
        set(resolved_constructors) - set(NATIVE_CONSTRUCTOR_NAMES)
    )
    if unsupported:
        raise ValueError(
            "detached Python constructors are not registered: {}".format(
                ", ".join(unsupported)
            )
        )
    namespace = {
        **INTERNAL_GLOBALS,
        **{name: context[name] for name in CONTEXT_FIELDS},
        **resolved_constructors,
    }
    namespace["__builtins__"] = detached_builtins()
    return namespace


def detached_python_registry(
    available_constructor_names: Iterable[str] = (),
) -> dict[str, Any]:
    constructors = tuple(
        sorted(set(str(name) for name in available_constructor_names))
    )
    unsupported = sorted(set(constructors) - set(NATIVE_CONSTRUCTOR_NAMES))
    if unsupported:
        raise ValueError(
            "detached Python constructors are not registered: {}".format(
                ", ".join(unsupported)
            )
        )
    snapshot = builtin_snapshot()
    detached = {
        "contractVersion": DETACHED_PYTHON_CONTRACT_VERSION,
        "appliesToModes": list(DETACHED_PYTHON_MODES),
        "baselinePython": snapshot["baselinePython"],
        "runtimePython": snapshot["runtimePython"],
        "builtins": list(public_builtin_names()),
        "internalBuiltins": sorted(INTERNAL_BUILTIN_NAMES),
        "internalGlobals": dict(INTERNAL_GLOBALS),
        "importRoots": sorted(ALLOWED_IMPORT_ROOTS),
        "context": {
            name: dict(CONTEXT_FIELDS[name]) for name in sorted(CONTEXT_FIELDS)
        },
        "constructors": list(constructors),
        "deniedCapabilities": {
            group: list(names)
            for group, names in sorted(DENIED_BUILTIN_GROUPS.items())
        },
        "builtinSnapshot": snapshot,
        "securityBoundary": "detached_clone_and_verified_application",
        "securitySandbox": False,
    }
    detached["deniedCapabilities"].update(
        {
            "dangerousImportRoots": sorted(DANGEROUS_IMPORT_ROOTS),
            "hostEffectMethods": sorted(HOST_EFFECT_METHOD_NAMES),
        }
    )
    detached["contractFingerprint"] = _sha_json(detached)
    return {
        "pythonModes": list(PYTHON_MODES),
        "pythonExecution": {"detachedNamespace": detached},
    }


def detached_python_registry_for_host(host: Any) -> dict[str, Any]:
    reader = getattr(host, "detached_python_constructor_names", None)
    names = tuple(reader()) if callable(reader) else ()
    return detached_python_registry(names)


__all__ = [
    "ALLOWED_IMPORT_ROOTS",
    "CONTEXT_FIELDS",
    "DANGEROUS_IMPORT_ROOTS",
    "DENIED_BUILTIN_GROUPS",
    "DENIED_BUILTIN_NAMES",
    "DETACHED_PYTHON_BASELINE",
    "DETACHED_PYTHON_CONTRACT_VERSION",
    "DETACHED_PYTHON_MODES",
    "INTERNAL_BUILTIN_NAMES",
    "INTERNAL_GLOBALS",
    "HOST_EFFECT_METHOD_NAMES",
    "NATIVE_CONSTRUCTOR_NAMES",
    "POLICY_FORBIDDEN_CALL_NAMES",
    "PYTHON_MODES",
    "StagedImportUnavailable",
    "build_detached_namespace",
    "builtin_snapshot",
    "detached_builtins",
    "detached_python_registry",
    "detached_python_registry_for_host",
    "public_builtin_names",
    "require_reviewed_builtin_snapshot",
    "unavailable_standard_builtin_names",
]
