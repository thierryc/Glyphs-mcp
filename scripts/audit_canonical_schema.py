#!/usr/bin/env python3
"""Independent, read-only closure audit for the canonical model schema."""

from __future__ import annotations

import argparse
import ast
import copy
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_runtime(repo: Path) -> None:
    for path in (repo / "src" / "glyphs-mcp-v2", repo / "scripts"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def audit(repo: Path, *, check_upstream: bool) -> dict[str, object]:
    _load_runtime(repo)
    from glyphs_mcp_v2.canonical_schema import (
        CANONICAL_SCHEMA,
        audit_official_schema,
        canonical_coverage_summary,
    )
    from glyphs_mcp_v2.canonical_sources import SerializedMappingSource
    from glyphs_mcp_v2.semantic import fingerprint_model
    from glyphs_mcp_v2.semantic import diff_models
    from release_security import validate_knowledge_dependencies

    knowledge = validate_knowledge_dependencies(
        repo, check_upstream=check_upstream
    )
    schema_path = repo / "third_party" / "glyphs-file-format-v4" / "glyphs-4.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    registry = audit_official_schema(schema, CANONICAL_SCHEMA)
    if not registry.complete:
        raise RuntimeError(
            "canonical registry is incomplete: unclassified={} stale={}".format(
                list(registry.unclassified[:20]),
                list(registry.stale_registry_entries[:20]),
            )
        )

    flat = {
        "fontMaster": [{"id": "M1", "name": "Regular"}],
        "unitsPerEm": 1000,
        "versionMajor": 1,
        "versionMinor": 0,
        "properties": [{"key": "familyNames", "value": "Audit"}],
        "glyphs": [
            {"glyphname": "A", "layers": [{"layerId": "M1", "width": 600}]}
        ],
    }
    package = {
        "fontinfo.plist": {
            key: value for key, value in flat.items() if key != "glyphs"
        },
        "glyphs": {"A": flat["glyphs"][0]},
        "order.plist": ["A"],
        "UIState.plist": {"displayStrings": ["ignored"]},
    }
    flat_model = SerializedMappingSource(flat).capture()
    package_model = SerializedMappingSource(package).capture()
    flat_fingerprint = fingerprint_model(flat_model)
    if flat_fingerprint != fingerprint_model(package_model):
        raise RuntimeError("flat/package canonical source fingerprints diverged")

    changed_model = copy.deepcopy(dict(flat_model))
    changed_model["font"]["note"] = "independent canonical audit"
    changed_model["glyphOrder"] = list(reversed(changed_model["glyphOrder"]))
    transition = diff_models(flat_model, changed_model)
    if transition.apply(flat_model) != changed_model:
        raise RuntimeError("independent canonical transition did not reproduce its target")
    if transition.inverse().apply(changed_model) != flat_model:
        raise RuntimeError("independent canonical inverse did not restore its baseline")

    source_path = (
        repo
        / "src"
        / "glyphs-mcp-v2"
        / "glyphs_mcp_v2"
        / "canonical_sources.py"
    )
    source_text = source_path.read_text(encoding="utf-8")
    if "import glyphsLib" in source_text or "from glyphsLib" in source_text:
        raise RuntimeError("runtime canonical source port gained a glyphsLib dependency")

    runtime_root = repo / "src" / "glyphs-mcp-v2" / "glyphs_mcp_v2"
    apply_target_definitions = []
    transaction_kernel_definitions = []
    glyphs_imports = []
    for path in runtime_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(runtime_root).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_apply_target_model":
                apply_target_definitions.append(relative)
            elif isinstance(node, ast.ClassDef) and node.name == "TransactionKernel":
                transaction_kernel_definitions.append(relative)
            elif isinstance(node, ast.ImportFrom) and str(node.module or "").startswith("GlyphsApp"):
                glyphs_imports.append(relative)
            elif isinstance(node, ast.Import):
                if any(alias.name == "GlyphsApp" for alias in node.names):
                    glyphs_imports.append(relative)
    if apply_target_definitions != ["adapters/document.py"]:
        raise RuntimeError(
            "canonical native replay must have one adapter implementation: {}".format(
                apply_target_definitions
            )
        )
    if transaction_kernel_definitions != ["transactions.py"]:
        raise RuntimeError(
            "verified mutation kernel is duplicated: {}".format(
                transaction_kernel_definitions
            )
        )
    allowed_glyphs_imports = {"change_diff_reporter.py", "change_log_panel.py"}
    unexpected_glyphs_imports = sorted(
        relative
        for relative in set(glyphs_imports) - allowed_glyphs_imports
        if not relative.startswith("adapters/")
    )
    if unexpected_glyphs_imports:
        raise RuntimeError(
            "native Glyphs imports escaped adapter/UI boundaries: {}".format(
                unexpected_glyphs_imports
            )
        )

    reporter_text = (runtime_root / "change_diff_reporter.py").read_text(encoding="utf-8")
    reporter_forbidden = (
        "native_font_to_model",
        "native_layer_to_model",
        "fingerprint_model",
        "diff_models",
        "capture_snapshot",
        "_apply_target_model",
    )
    present = [value for value in reporter_forbidden if value in reporter_text]
    if present:
        raise RuntimeError(
            "Reporter performs canonical capture, hashing, or mutation work: {}".format(present)
        )

    registry_consumers = {}
    for relative in ("canonical_sources.py", "adapters/document.py", "mutation.py"):
        text = (runtime_root / relative).read_text(encoding="utf-8")
        registry_consumers[relative] = "CANONICAL_SCHEMA.fields_for" in text
    if not all(registry_consumers.values()):
        raise RuntimeError(
            "canonical registry is not consumed by every capture/replay/planning boundary: {}".format(
                registry_consumers
            )
        )

    summary = canonical_coverage_summary(schema)
    return {
        "status": "passed",
        "knowledge": knowledge,
        "coverage": summary,
        "flattenedFieldSpecCount": len(CANONICAL_SCHEMA.field_specs),
        "sourceNeutralFixtureFingerprint": flat_fingerprint,
        "runtimeGlyphsLibDependency": False,
        "architecturalChecks": {
            "singleNativeReplayAdapter": True,
            "singleVerifiedMutationKernel": True,
            "nativeImportsBoundedToAdaptersAndUI": True,
            "reporterCanonicalWork": False,
            "registryConsumers": registry_consumers,
            "independentTransitionRoundTrip": True,
        },
        "checkUpstream": bool(check_upstream),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=_repo_root())
    parser.add_argument("--check-upstream", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    result = audit(args.repo_root.resolve(), check_upstream=args.check_upstream)
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"))
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
