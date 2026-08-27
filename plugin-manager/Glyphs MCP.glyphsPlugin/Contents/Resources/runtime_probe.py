#!/usr/bin/env python3
"""Inspect the Python runtime used by Glyphs MCP.

This script intentionally uses only the Python standard library. Installers run
it with the exact interpreter selected for a Glyphs target and consume the JSON
document written to stdout.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import platform
import re
import site
import subprocess
import sys
import sysconfig
import traceback
import warnings
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from runtime_path_policy import (
        apply_runtime_path_plan,
        build_runtime_path_plan,
        classify_origin,
    )
except ModuleNotFoundError:
    resources_directory = str(Path(__file__).resolve().parent)
    if resources_directory not in sys.path:
        sys.path.insert(0, resources_directory)
    from runtime_path_policy import (  # type: ignore[no-redef]
        apply_runtime_path_plan,
        build_runtime_path_plan,
        classify_origin,
    )


SCHEMA_VERSION = 1
DEFAULT_MODULES = [
    "mcp",
    "fastmcp",
    "pydantic_core",
    "starlette",
    "uvicorn",
    "httpx",
    "sse_starlette",
    "typing_extensions",
    "pkg_resources",
    "fontParts",
    "fontTools",
    "objc",
    "Foundation",
    "AppKit",
    "_cffi_backend",
    "rpds",
]
CPYTHON_TAG = re.compile(r"(?:^|[._-])cpython-(\d{2,3})(?:[._-]|$)")
NATIVE_SUFFIXES = (".so", ".dylib")


def _normalise_architecture(value: str) -> str:
    value = value.strip().lower()
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "aarch64": "arm64",
        "arm64e": "arm64",
    }
    return aliases.get(value, value)


def _runtime() -> Dict[str, str]:
    return {
        "executable": sys.executable,
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "soabi": sysconfig.get_config_var("SOABI") or "",
        "extensionSuffix": sysconfig.get_config_var("EXT_SUFFIX") or "",
        "architecture": _normalise_architecture(platform.machine()),
    }


def _candidate_cpython_tag(path: Path) -> Optional[str]:
    match = CPYTHON_TAG.search(path.name)
    return match.group(1) if match else None


def _expected_cpython_tag() -> str:
    return f"{sys.version_info.major}{sys.version_info.minor}"


def _macho_architectures(path: Path) -> List[str]:
    """Return Mach-O architectures when lipo can identify the file."""
    lipo = Path("/usr/bin/lipo")
    if not lipo.is_file():
        return []
    try:
        completed = subprocess.run(
            [str(lipo), "-archs", str(path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    return sorted(
        {
            _normalise_architecture(value)
            for value in completed.stdout.split()
            if value.strip()
        }
    )


def _is_abi_compatible(path: Path, expected_tag: str) -> Tuple[bool, str]:
    name = path.name
    if ".abi3." in name:
        return True, "abi3"
    detected = _candidate_cpython_tag(path)
    if detected is None:
        return True, "untagged"
    return detected == expected_tag, f"cpython-{detected}"


def _is_architecture_compatible(
    architectures: Sequence[str], expected_architecture: str
) -> bool:
    if not architectures:
        return True
    normalised = {_normalise_architecture(value) for value in architectures}
    return _normalise_architecture(expected_architecture) in normalised


def _module_paths(root: Path, module: str) -> List[Path]:
    top_level = module.split(".", 1)[0]
    package = root / top_level
    candidates: List[Path] = []
    if package.is_dir():
        candidates.append(package)
    py_file = root / f"{top_level}.py"
    if py_file.is_file():
        candidates.append(py_file)
    for suffix in NATIVE_SUFFIXES:
        candidates.extend(sorted(root.glob(f"{top_level}*{suffix}")))
    return candidates


def _native_files(paths: Iterable[Path]) -> List[Path]:
    files: List[Path] = []
    for path in paths:
        if path.is_file() and path.name.endswith(NATIVE_SUFFIXES):
            files.append(path)
        elif path.is_dir():
            for suffix in NATIVE_SUFFIXES:
                files.extend(sorted(path.rglob(f"*{suffix}")))
    return sorted(set(files))


def _is_within(path: str, roots: Sequence[Path]) -> bool:
    if not path or path in {"built-in", "frozen", "namespace"}:
        return False
    try:
        candidate = Path(path).resolve()
    except OSError:
        return False
    for root in roots:
        try:
            candidate.relative_to(root.resolve())
            return True
        except (OSError, ValueError):
            continue
    return False


def _issue(
    code: str,
    module: str,
    message: str,
    *,
    path: Optional[Path] = None,
    expected: Optional[str] = None,
    detected: Optional[str] = None,
    blocking: bool = True,
    **details: Any,
) -> Dict[str, Any]:
    issue = {
        "code": code,
        "module": module,
        "file": str(path) if path else None,
        "expected": expected,
        "detected": detected,
        "message": message,
        "blocking": blocking,
    }
    issue.update(details)
    return issue


def _prepare_paths(plan: Dict[str, Any]) -> None:
    apply_runtime_path_plan(plan)
    importlib.invalidate_caches()


def _module_was_found(module: str, roots: Sequence[Path]) -> bool:
    if any(_module_paths(root, module) for root in roots if root.exists()):
        return True
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return True


def _clear_module(module: str) -> None:
    top_level = module.split(".", 1)[0]
    for loaded in list(sys.modules):
        if loaded == top_level or loaded.startswith(top_level + "."):
            sys.modules.pop(loaded, None)


def _check_module(
    module: str,
    *,
    mode: str,
    plan: Dict[str, Any],
    expected_tag: str,
    expected_architecture: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    inspected_roots = [Path(value) for value in plan["orderedRoots"]]
    candidates: List[Dict[str, Any]] = []
    for index, root in enumerate(inspected_roots):
        module_paths = _module_paths(root, module)
        if not module_paths:
            continue
        native_details: List[Dict[str, Any]] = []
        for path in _native_files(module_paths):
            abi_ok, abi = _is_abi_compatible(path, expected_tag)
            architectures = _macho_architectures(path)
            arch_ok = _is_architecture_compatible(architectures, expected_architecture)
            native_details.append(
                {
                    "file": str(path),
                    "abi": abi,
                    "abiCompatible": abi_ok,
                    "architectures": architectures,
                    "architectureCompatible": arch_ok,
                }
            )
        candidates.append(
            {
                "root": str(root),
                "priority": index,
                "paths": [str(path) for path in module_paths],
                "nativeFiles": native_details,
            }
        )
    winner = candidates[0] if candidates else None
    native_details = winner["nativeFiles"] if winner else []

    present = bool(winner) or _module_was_found(module, inspected_roots)
    imported = False
    origin: Optional[str] = None
    error: Optional[str] = None
    exception_name: Optional[str] = None
    with warnings.catch_warnings(record=True) as emitted_warnings:
        # Python warnings normally go to stderr. Preserve them in the JSON log
        # so installer wrappers can continue treating unstructured stderr as a
        # fatal, unverifiable probe failure without rejecting benign package
        # deprecation warnings.
        warnings.simplefilter("always")
        try:
            _clear_module(module)
            imported_module = importlib.import_module(module)
            origin = getattr(imported_module, "__file__", None)
            if not origin:
                spec = getattr(imported_module, "__spec__", None)
                origin = getattr(spec, "origin", None) if spec else None
            imported = True
            if module == "mcp":
                mcp_types = importlib.import_module("mcp.types")
                if not hasattr(mcp_types, "AnyFunction"):
                    raise ImportError("mcp.types.AnyFunction is missing (upgrade mcp)")
        except Exception as exc:  # the exact import error belongs in the JSON log
            error = f"{type(exc).__name__}: {exc}"
            exception_name = getattr(exc, "name", None)
            imported = False
    captured_warnings = [
        f"{warning.category.__name__}: {warning.message}"
        for warning in emitted_warnings
    ]

    issues: List[Dict[str, Any]] = []
    deferred_warnings: List[Dict[str, Any]] = []
    for candidate_index, candidate in enumerate(candidates):
        if candidate_index > 0:
            issues.append(
                _issue(
                    "shadowed_duplicate",
                    module,
                    f"A lower-priority copy of {module} is shadowed by {winner['root']}.",
                    path=Path(candidate["paths"][0]),
                    blocking=False,
                    winningCandidate=winner,
                    lowerPriorityCandidate=candidate,
                )
            )
        for detail in candidate["nativeFiles"]:
            has_compatible_native = any(
                item["abiCompatible"] and item["architectureCompatible"]
                for item in candidate["nativeFiles"]
            )
            blocking_native = candidate_index == 0 and not has_compatible_native
            if not detail["abiCompatible"]:
                path = Path(detail["file"])
                native_issue = _issue(
                        "incompatible_abi",
                        module,
                        f"{path.name} was built for {detail['abi']}, but this interpreter requires CPython {expected_tag}.",
                        path=path,
                        expected=f"cpython-{expected_tag} or abi3",
                        detected=detail["abi"],
                        blocking=blocking_native,
                        selectedRoot=candidate["root"],
                        winningCandidate=winner,
                    )
                (issues if blocking_native else deferred_warnings).append(native_issue)
            if not detail["architectureCompatible"]:
                path = Path(detail["file"])
                detected = ", ".join(detail["architectures"])
                native_issue = _issue(
                        "incompatible_architecture",
                        module,
                        f"{path.name} supports {detected}, but this interpreter is running as {expected_architecture}.",
                        path=path,
                        expected=expected_architecture,
                        detected=detected,
                        blocking=blocking_native,
                        selectedRoot=candidate["root"],
                        winningCandidate=winner,
                    )
                (issues if blocking_native else deferred_warnings).append(native_issue)
    missing = (
        not present
        and exception_name in {module, module.split(".", 1)[0]}
    )
    if not imported:
        if mode == "preinstall" and missing:
            issues.append(
                _issue(
                    "missing_module",
                    module,
                    f"{module} is not installed yet.",
                    blocking=False,
                )
            )
        else:
            if not any(issue["blocking"] for issue in issues):
                code = "missing_module" if missing else "import_failure"
                diagnostic_path: Optional[Path] = None
                compatible_native = next(
                    (
                        detail["file"]
                        for detail in native_details
                        if detail["abiCompatible"] and detail["architectureCompatible"]
                    ),
                    None,
                )
                if compatible_native:
                    diagnostic_path = Path(compatible_native)
                elif winner and winner["paths"]:
                    diagnostic_path = Path(winner["paths"][0])
                issues.append(
                    _issue(
                        code,
                        module,
                        f"{module} could not be imported: {error or 'unknown error'}",
                        path=diagnostic_path,
                        expected="successful import",
                        detected=error or "unknown error",
                        blocking=True,
                    )
                )
    elif origin and origin not in {"built-in", "frozen", "namespace"}:
        classification = classify_origin(origin, plan)
        if not classification["accepted"]:
            classification_details = {
                key: value
                for key, value in classification.items()
                if key not in {"code", "blocking"}
            }
            issues.append(
                _issue(
                    classification["code"],
                    module,
                    f"{module} imported from a dependency location outside the approved runtime roots.",
                    path=Path(origin),
                    expected=", ".join(plan["orderedRoots"]),
                    detected=classification["resolvedOrigin"],
                    **classification_details,
                )
            )
    if winner and winner["priority"] > 0:
        issues.append(
            _issue(
                "fallback_selected",
                module,
                f"{module} is using fallback root {winner['root']} because no higher-priority copy exists.",
                path=Path(winner["paths"][0]),
                blocking=False,
                selectedRoot=winner["root"],
                winningCandidate=winner,
            )
        )
    issues.extend(deferred_warnings)

    return (
        {
            "module": module,
            "present": present,
            "imported": imported,
            "origin": origin,
            "logicalOrigin": str(Path(origin).absolute()) if origin and origin not in {"built-in", "frozen", "namespace"} else origin,
            "resolvedOrigin": str(Path(origin).resolve()) if origin and origin not in {"built-in", "frozen", "namespace"} else origin,
            "error": error,
            "warnings": captured_warnings,
            "nativeFiles": native_details,
            "selectedRoot": winner["root"] if winner else None,
            "winningCandidate": winner,
            "lowerPriorityCandidates": candidates[1:],
        },
        issues,
    )


def run_probe(
    *,
    mode: str,
    site_packages: Path,
    additional_paths: Sequence[Path] = (),
    allowed_origins: Sequence[Path] = (),
    modules: Sequence[str] = DEFAULT_MODULES,
    allow_user_site: bool = False,
    allow_runtime_paths: bool = False,
) -> Dict[str, Any]:
    runtime = _runtime()
    plan = build_runtime_path_plan(site_packages, executable=sys.executable)
    # Legacy flags remain parseable. Additional explicitly managed paths are
    # appended without changing the primary/install-mode decision.
    legacy_roots = [Path(path) for path in additional_paths]
    if legacy_roots:
        existing = list(plan["orderedRoots"])
        for root in legacy_roots:
            if str(root) not in existing:
                existing.append(str(root))
        plan["orderedRoots"] = existing
        plan["fallbackRoots"] = existing[1:]
    _prepare_paths(plan)

    checks: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    for module in modules:
        check, module_issues = _check_module(
            module,
            mode=mode,
            plan=plan,
            expected_tag=_expected_cpython_tag(),
            expected_architecture=runtime["architecture"],
        )
        checks.append(check)
        issues.extend(module_issues)

    blocking = any(issue["blocking"] for issue in issues)
    incomplete = any(issue["code"] == "missing_module" for issue in issues)
    status = "incompatible" if blocking else "incomplete" if incomplete else "ok"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "mode": mode,
        "status": status,
        "blocking": blocking,
        "runtime": runtime,
        "pathPlan": plan,
        "sitePackages": str(site_packages),
        "allowedOrigins": list(plan["orderedRoots"]),
        "checks": checks,
        "issues": issues,
    }


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preinstall", "postinstall"), required=True)
    parser.add_argument("--site-packages", type=Path, required=True)
    parser.add_argument("--additional-path", action="append", type=Path, default=[])
    parser.add_argument("--allow-origin", action="append", type=Path, default=[])
    parser.add_argument("--allow-user-site", action="store_true")
    parser.add_argument("--allow-runtime-paths", action="store_true")
    parser.add_argument("--module", action="append", default=[])
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_probe(
            mode=args.mode,
            site_packages=args.site_packages,
            additional_paths=args.additional_path,
            allowed_origins=args.allow_origin,
            modules=args.module or DEFAULT_MODULES,
            allow_user_site=args.allow_user_site,
            allow_runtime_paths=args.allow_runtime_paths,
        )
    except Exception as exc:
        result = {
            "schemaVersion": SCHEMA_VERSION,
            "mode": args.mode,
            "status": "error",
            "blocking": True,
            "runtime": _runtime(),
            "sitePackages": str(args.site_packages),
            "checks": [],
            "issues": [
                _issue(
                    "probe_failure",
                    "runtime_probe",
                    f"Runtime probe failed: {type(exc).__name__}: {exc}",
                )
            ],
            "traceback": traceback.format_exc(),
        }
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 2 if result.get("blocking") else 0


if __name__ == "__main__":
    raise SystemExit(main())
