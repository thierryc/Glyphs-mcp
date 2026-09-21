"""Closed contracts for feature compilation and staged font export jobs."""

from __future__ import annotations

import json
import math
import re
from pathlib import PurePosixPath
from typing import Any, Mapping

from .models import PATCH_VERSION, ProtocolError, validate_patch


JOB_CAPABILITIES = (
    "feature.compile.live.v1",
    "feature.compile.saved.v1",
    "font.export.static.v1",
    "font.export.variable.v1",
    "font.export.web.v1",
    "font.verify.shaping.v1",
    "font.verify.tables.v1",
)

MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_ARTIFACT_FILES = 3
MAX_ARTIFACT_FILE_BYTES = 512 * 1024 * 1024
MAX_ARTIFACT_JOB_BYTES = 1024 * 1024 * 1024
MAX_SHAPING_CASES = 32
MAX_SHAPING_TEXT = 256

_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_TAG = re.compile(r"^[\x20-\x7e]{4}$")


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolError("invalid_request", f"{label} must be an object")
    return value


def _closed(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unexpected = sorted(set(value) - allowed)
    if unexpected:
        raise ProtocolError(
            "invalid_request", f"{label} has unexpected fields: {', '.join(unexpected)}"
        )


def _text(value: Any, label: str, *, maximum: int = 255) -> str:
    if not isinstance(value, str):
        raise ProtocolError("invalid_request", f"{label} must be a string")
    result = value.strip()
    if not result or len(result) > maximum:
        raise ProtocolError("invalid_request", f"{label} must be 1-{maximum} characters")
    return result


def _hash(value: Any, label: str) -> str:
    result = str(value or "")
    if not _HASH.fullmatch(result):
        raise ProtocolError("invalid_request", f"{label} must be a SHA-256 fingerprint")
    return result


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ProtocolError("invalid_request", f"{label} must be a boolean")
    return value


def recognized_job_capabilities(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(
        {item for item in value if isinstance(item, str) and item in JOB_CAPABILITIES}
    )


def validate_compile_options(value: Any) -> dict[str, Any]:
    options = _object(value, "feature_compile options")
    _closed(options, {"mode"}, "feature_compile options")
    mode = options.get("mode", "saved")
    if mode not in ("saved", "live"):
        raise ProtocolError("invalid_request", "feature_compile mode must be saved or live")
    return {"mode": mode}


def _shaping_case(value: Any, index: int) -> dict[str, Any]:
    case = _object(value, f"shaping case {index}")
    allowed = {
        "text", "feature", "expect", "controlText", "value",
        "direction", "script", "language", "variations",
    }
    _closed(case, allowed, f"shaping case {index}")
    if not {"text", "feature", "expect"}.issubset(case):
        raise ProtocolError("invalid_request", "shaping cases require text, feature and expect")
    text = _text(case.get("text"), "shaping text", maximum=MAX_SHAPING_TEXT)
    feature = case.get("feature")
    if not isinstance(feature, str) or not _TAG.fullmatch(feature):
        raise ProtocolError(
            "invalid_request", "shaping feature must be four printable ASCII characters"
        )
    expectation = case.get("expect")
    if expectation not in ("different", "same"):
        raise ProtocolError("invalid_request", "shaping expect must be different or same")
    result: dict[str, Any] = {"text": text, "feature": feature, "expect": expectation}
    if "controlText" in case:
        result["controlText"] = _text(
            case.get("controlText"), "shaping controlText", maximum=MAX_SHAPING_TEXT
        )
    feature_value = case.get("value", 1)
    if isinstance(feature_value, bool) or not isinstance(feature_value, int) or not 1 <= feature_value <= 99:
        raise ProtocolError("invalid_request", "shaping feature value must be an integer from 1 to 99")
    result["value"] = feature_value
    if "direction" in case:
        direction = case.get("direction")
        if direction not in ("ltr", "rtl", "ttb", "btt"):
            raise ProtocolError("invalid_request", "shaping direction must be ltr, rtl, ttb or btt")
        result["direction"] = direction
    for name in ("script", "language"):
        if name in case:
            result[name] = _text(case.get(name), f"shaping {name}", maximum=16)
    if "variations" in case:
        variations = _object(case.get("variations"), "shaping variations")
        if len(variations) > 32:
            raise ProtocolError("invalid_request", "shaping variations accept at most 32 axes")
        normalized = {}
        for tag, raw in variations.items():
            if not isinstance(tag, str) or not _TAG.fullmatch(tag):
                raise ProtocolError("invalid_request", "variation axis tags must be four printable ASCII characters")
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
                raise ProtocolError("invalid_request", "variation coordinates must be finite numbers")
            normalized[tag] = raw
        result["variations"] = normalized
    return result


def validate_export_options(value: Any) -> dict[str, Any]:
    options = _object(value, "font_export options")
    _closed(
        options,
        {"instanceId", "format", "containers", "generation", "verification"},
        "font_export options",
    )
    if not {"instanceId", "format"}.issubset(options):
        raise ProtocolError("invalid_request", "font_export requires instanceId and format")
    instance_id = _text(options.get("instanceId"), "font_export instanceId")
    font_format = options.get("format")
    if font_format not in ("otf", "ttf"):
        raise ProtocolError("invalid_request", "font_export format must be otf or ttf")

    containers = options.get("containers", ["plain"])
    if not isinstance(containers, list) or not 1 <= len(containers) <= 3:
        raise ProtocolError("invalid_request", "containers must contain 1-3 values")
    if any(item not in ("plain", "woff", "woff2") for item in containers):
        raise ProtocolError("invalid_request", "containers must be plain, woff or woff2")
    if len(containers) != len(set(containers)):
        raise ProtocolError("invalid_request", "containers must be unique")

    supplied_generation = options.get("generation", {})
    generation = _object(supplied_generation, "font_export generation")
    generation_fields = {
        "autoHint", "removeOverlap", "useSubroutines",
        "useProductionNames", "decomposeSmartComponents",
    }
    _closed(generation, generation_fields, "font_export generation")
    normalized_generation = {
        "autoHint": True,
        "removeOverlap": None,
        "useSubroutines": font_format == "otf",
        "useProductionNames": True,
        "decomposeSmartComponents": True,
    }
    for name in generation_fields:
        if name in generation:
            normalized_generation[name] = _boolean(generation[name], f"font_export {name}")
    if font_format == "ttf" and generation.get("useSubroutines") is True:
        raise ProtocolError("invalid_request", "useSubroutines is unavailable for TTF export")

    verification = _object(options.get("verification", {}), "font_export verification")
    _closed(verification, {"shapingCases"}, "font_export verification")
    cases = verification.get("shapingCases", [])
    if not isinstance(cases, list) or len(cases) > MAX_SHAPING_CASES:
        raise ProtocolError("invalid_request", "shapingCases must contain 0-32 cases")

    return {
        "instanceId": instance_id,
        "format": font_format,
        "containers": list(containers),
        "generation": normalized_generation,
        "verification": {
            "shapingCases": [_shaping_case(item, index) for index, item in enumerate(cases)]
        },
    }


def _report(value: Any) -> dict[str, Any]:
    report = _object(value, "worker report")
    try:
        encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProtocolError("invalid_request", "worker report must be bounded JSON") from exc
    if len(encoded) > MAX_REPORT_BYTES:
        raise ProtocolError("invalid_request", "worker report exceeds 8 MiB")
    return dict(report)


def _manifest(value: Any) -> dict[str, Any]:
    manifest = _object(value, "artifact manifest")
    _closed(manifest, {"files", "totalBytes"}, "artifact manifest")
    files = manifest.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_ARTIFACT_FILES:
        raise ProtocolError("invalid_request", "artifact manifest requires 1-3 files")
    normalized = []
    paths = set()
    total = 0
    for index, raw in enumerate(files):
        item = _object(raw, f"artifact file {index}")
        fields = {"path", "size", "sha256", "format", "container", "mediaType"}
        _closed(item, fields, f"artifact file {index}")
        if set(item) != fields:
            raise ProtocolError("invalid_request", "artifact file fields are incomplete")
        path = item.get("path")
        if not isinstance(path, str) or not path or len(path) > 4096:
            raise ProtocolError("invalid_request", "artifact paths must be nonempty relative paths")
        parsed = PurePosixPath(path)
        if parsed.is_absolute() or any(part in ("", ".", "..") for part in parsed.parts):
            raise ProtocolError("invalid_request", "artifact paths must be safe relative paths")
        if path in paths:
            raise ProtocolError("invalid_request", "artifact paths must be unique")
        paths.add(path)
        size = item.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_ARTIFACT_FILE_BYTES:
            raise ProtocolError("invalid_request", "artifact file size exceeds 512 MiB")
        font_format = item.get("format")
        container = item.get("container")
        if font_format not in ("otf", "ttf") or container not in ("plain", "woff", "woff2"):
            raise ProtocolError("invalid_request", "artifact format or container is unsupported")
        total += size
        normalized.append({
            "path": path,
            "size": size,
            "sha256": _hash(item.get("sha256"), "artifact sha256"),
            "format": font_format,
            "container": container,
            "mediaType": _text(item.get("mediaType"), "artifact mediaType", maximum=120),
        })
    if total > MAX_ARTIFACT_JOB_BYTES:
        raise ProtocolError("invalid_request", "artifact job exceeds 1 GiB")
    declared = manifest.get("totalBytes")
    if isinstance(declared, bool) or not isinstance(declared, int) or declared != total:
        raise ProtocolError("invalid_request", "artifact totalBytes does not match its files")
    return {"files": normalized, "totalBytes": total}


def validate_artifact_manifest(value: Any) -> dict[str, Any]:
    return _manifest(value)


def validate_worker_result(value: Any) -> dict[str, Any]:
    """Validate internal worker output without exposing an object protocol."""

    candidate = _object(value, "worker result")
    if "resultKind" not in candidate:
        return {"resultKind": "mutation", "patch": validate_patch(candidate)}
    kind = candidate.get("resultKind")
    if kind == "mutation":
        _closed(candidate, {"resultKind", "patch"}, "mutation worker result")
        return {"resultKind": "mutation", "patch": validate_patch(candidate.get("patch"))}
    common = {
        "version", "resultKind", "jobId", "documentId", "sourcePath",
        "sourceHash", "generation", "summary", "report",
    }
    allowed = common | ({"manifest"} if kind == "artifact" else set())
    _closed(candidate, allowed, "worker result")
    if kind not in ("diagnostic", "artifact"):
        raise ProtocolError("invalid_request", "worker resultKind must be mutation, diagnostic or artifact")
    if set(candidate) != allowed:
        raise ProtocolError("invalid_request", "worker result fields are incomplete")
    if candidate.get("version") != PATCH_VERSION:
        raise ProtocolError("unsupported_version", "unsupported worker result version")
    generation = candidate.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise ProtocolError("invalid_request", "worker result generation must be non-negative")
    result = {
        "version": PATCH_VERSION,
        "resultKind": kind,
        "jobId": _text(candidate.get("jobId"), "worker jobId", maximum=100),
        "documentId": _text(candidate.get("documentId"), "worker documentId", maximum=100),
        "sourcePath": _text(candidate.get("sourcePath"), "worker sourcePath", maximum=4096),
        "sourceHash": _hash(candidate.get("sourceHash"), "worker sourceHash"),
        "generation": generation,
        "summary": _text(candidate.get("summary"), "worker summary", maximum=2000),
        "report": _report(candidate.get("report")),
    }
    if kind == "artifact":
        result["manifest"] = _manifest(candidate.get("manifest"))
    return result
