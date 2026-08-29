#!/usr/bin/env python3
"""Verify installed Glyphs 4 runtime and Codex cache against repository builds."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable


REPO = Path(__file__).resolve().parents[1]
EXPECTED_BUNDLE = (
    REPO
    / "build/installer-payload/Payload/Plugins/Glyphs4/Glyphs MCP.glyphsPlugin"
)
EXPECTED_CODEX_PLUGIN = REPO / "plugins/glyphs-mcp"
IGNORED_NAMES = {".DS_Store", "__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}
RETIRED_TOOLS = {
    "list_open_fonts",
    "get_document_status",
    "review_spacing",
    "apply_spacing",
    "rollback_python_execution",
}


def _files(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise ValueError("directory is missing: {}".format(root))
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_NAMES for part in relative.parts):
            continue
        if path.suffix in IGNORED_SUFFIXES:
            continue
        result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _mismatch(expected: dict[str, str], observed: dict[str, str]) -> dict[str, object]:
    expected_names = set(expected)
    observed_names = set(observed)
    changed = sorted(
        name
        for name in expected_names & observed_names
        if expected[name] != observed[name]
    )
    return {
        "missing": sorted(expected_names - observed_names),
        "unexpected": sorted(observed_names - expected_names),
        "changed": changed,
    }


def _clean(mismatch: dict[str, object]) -> bool:
    return not any(mismatch.values())


def _retired_skill_names(root: Path) -> list[str]:
    skills = root / "skills"
    violations: list[str] = []
    for path in sorted(skills.rglob("*")) if skills.is_dir() else ():
        if not path.is_file() or path.suffix not in {".md", ".json", ".yaml", ".yml"}:
            continue
        text = path.read_text(encoding="utf-8")
        for name in sorted(RETIRED_TOOLS):
            if name in text:
                violations.append("{}:{}".format(path.relative_to(root), name))
    return violations


def verify(
    runtime_bundle: Path,
    codex_cache: Path,
    *,
    expected_runtime_bundle: Path = EXPECTED_BUNDLE,
) -> dict[str, object]:
    runtime_mismatch = _mismatch(
        _files(expected_runtime_bundle), _files(runtime_bundle)
    )
    cache_mismatch = _mismatch(
        _files(EXPECTED_CODEX_PLUGIN), _files(codex_cache)
    )
    retired = _retired_skill_names(codex_cache)
    return {
        "ok": _clean(runtime_mismatch) and _clean(cache_mismatch) and not retired,
        "expectedRuntimeBundle": str(expected_runtime_bundle),
        "runtimeBundle": str(runtime_bundle),
        "codexCache": str(codex_cache),
        "runtimeMismatch": runtime_mismatch,
        "codexCacheMismatch": cache_mismatch,
        "retiredSkillReferences": retired,
    }


def main(arguments: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-bundle", type=Path, required=True)
    parser.add_argument(
        "--expected-runtime-bundle",
        type=Path,
        default=EXPECTED_BUNDLE,
        help="freshly built installable Glyphs 4 bundle to compare",
    )
    parser.add_argument("--codex-cache", type=Path, required=True)
    parsed = parser.parse_args(arguments)
    try:
        report = verify(
            parsed.runtime_bundle.resolve(),
            parsed.codex_cache.resolve(),
            expected_runtime_bundle=parsed.expected_runtime_bundle.resolve(),
        )
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
