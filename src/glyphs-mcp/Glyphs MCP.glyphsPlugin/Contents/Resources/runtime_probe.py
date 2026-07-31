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
NATIVE_MODULES = {"pydantic_core", "objc", "_cffi_backend", "rpds"}
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
) -> Dict[str, Any]:
    return {
        "code": code,
        "module": module,
        "file": str(path) if path else None,
        "expected": expected,
        "detected": detected,
        "message": message,
        "blocking": blocking,
    }


def _prepare_paths(site_packages: Path, additional_paths: Sequence[Path]) -> None:
    ordered = [site_packages, *additional_paths]
    for root in reversed(ordered):
        value = str(root)
        if not root.exists():
            continue
        site.addsitedir(value)
        while value in sys.path:
            sys.path.remove(value)
        sys.path.insert(0, value)
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
    inspected_roots: Sequence[Path],
    allowed_origins: Sequence[Path],
    expected_tag: str,
    expected_architecture: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    module_paths: List[Path] = []
    for root in inspected_roots:
        module_paths.extend(_module_paths(root, module))
    native_files = _native_files(module_paths)
    native_details: List[Dict[str, Any]] = []
    incompatible_abi: List[Tuple[Path, str]] = []
    incompatible_arch: List[Tuple[Path, List[str]]] = []
    for path in native_files:
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
        if not abi_ok:
            incompatible_abi.append((path, abi))
        if not arch_ok:
            incompatible_arch.append((path, architectures))

    present = _module_was_found(module, inspected_roots)
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
    compatible_native = [
        detail
        for detail in native_details
        if detail["abiCompatible"] and detail["architectureCompatible"]
    ]
    # A compatible module elsewhere on sys.path must not hide stale native
    # files in Glyphs' explicitly inspected shared target. For the native
    # runtime modules, report a target mismatch even when Python falls through
    # to a same-named user- or system-site package.
    report_static_native_mismatch = not imported or module in NATIVE_MODULES
    if report_static_native_mismatch and incompatible_abi and not compatible_native:
        for path, detected in incompatible_abi:
            issues.append(
                _issue(
                    "incompatible_abi",
                    module,
                    (
                        f"{path.name} was built for {detected}, but "
                        f"this interpreter requires CPython {expected_tag}."
                    ),
                    path=path,
                    expected=f"cpython-{expected_tag} or abi3",
                    detected=detected,
                )
            )
    if report_static_native_mismatch and incompatible_arch and not compatible_native:
        for path, architectures in incompatible_arch:
            detected = ", ".join(architectures)
            issues.append(
                _issue(
                    "incompatible_architecture",
                    module,
                    (
                        f"{path.name} supports {detected}, but this "
                        f"interpreter is running as {expected_architecture}."
                    ),
                    path=path,
                    expected=expected_architecture,
                    detected=detected,
                )
            )
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
                if compatible_native:
                    diagnostic_path = Path(compatible_native[0]["file"])
                elif module_paths:
                    diagnostic_path = module_paths[0]
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
    elif mode == "postinstall" and allowed_origins and not _is_within(
        origin or "", allowed_origins
    ):
        issues.append(
            _issue(
                "unexpected_origin",
                module,
                f"{module} imported from an unexpected location: {origin or 'unknown'}",
                path=Path(origin) if origin else None,
                expected=", ".join(str(path) for path in allowed_origins),
                detected=origin or "unknown",
            )
        )

    return (
        {
            "module": module,
            "present": present,
            "imported": imported,
            "origin": origin,
            "error": error,
            "warnings": captured_warnings,
            "nativeFiles": native_details,
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
    additional = [Path(path) for path in additional_paths]
    inspected_roots = [site_packages, *additional]
    allowed = [Path(path) for path in allowed_origins]
    if allow_user_site:
        user_site = site.getusersitepackages()
        if isinstance(user_site, str) and user_site:
            allowed.append(Path(user_site))
    if allow_runtime_paths:
        for value in sys.path:
            if value and Path(value).is_dir():
                allowed.append(Path(value))
    _prepare_paths(site_packages, additional)

    checks: List[Dict[str, Any]] = []
    issues: List[Dict[str, Any]] = []
    for module in modules:
        check, module_issues = _check_module(
            module,
            mode=mode,
            inspected_roots=inspected_roots,
            allowed_origins=allowed,
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
        "sitePackages": str(site_packages),
        "allowedOrigins": [str(path) for path in allowed],
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
