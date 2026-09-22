"""The complete v2 sidecar/bridge wire contract.

The format is deliberately handwritten and small.  It describes explicit
targets only; it is not a second font model or a remote-object protocol.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping


PROTOCOL_VERSION = 1
PATCH_VERSION = 1
TOOL_NAMES = (
    "get_status",
    "list_documents",
    "read_entities",
    "start_job",
    "get_job",
    "apply_job",
    "accept_job",
    "discard_job",
    "save_document",
    "start_edit_workflow",
    "get_edit_workflow",
    "respond_edit_workflow",
)

MAX_CHANGES = 100_000
MAX_SUMMARY_LENGTH = 2_000
SET_FIELDS = frozenset(
    {
        "width",
        "vertWidth",
        "vertOrigin",
        "leftMetricsKey",
        "rightMetricsKey",
        "widthMetricsKey",
    }
)
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_SCALAR_TYPES = (str, int, float, bool, type(None))


class ProtocolError(ValueError):
    """A closed-contract validation failure with a stable error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
    result = str(value or "").strip()
    if not result or len(result) > maximum:
        raise ProtocolError("invalid_request", f"{label} must be 1-{maximum} characters")
    return result


def _hash(value: Any, label: str) -> str:
    result = str(value or "")
    if not _HASH.fullmatch(result):
        raise ProtocolError("invalid_request", f"{label} must be a SHA-256 fingerprint")
    return result


def _number(value: Any, label: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolError("invalid_request", f"{label} must be a finite number")
    if not math.isfinite(float(value)):
        raise ProtocolError("invalid_request", f"{label} must be a finite number")
    return value


def _scalar(value: Any, label: str) -> Any:
    if not isinstance(value, _SCALAR_TYPES):
        raise ProtocolError("invalid_request", f"{label} must be a JSON scalar")
    if isinstance(value, float) and not math.isfinite(value):
        raise ProtocolError("invalid_request", f"{label} must be finite")
    return value


def _set_change(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"kind", "glyph", "layer", "field", "before", "after"}
    _closed(value, allowed, "set change")
    if set(value) != allowed:
        raise ProtocolError("invalid_request", "set change fields are incomplete")
    field = _text(value.get("field"), "set field", maximum=80)
    if field not in SET_FIELDS:
        raise ProtocolError("unsupported_change", f"unsupported set field: {field}")
    before = _scalar(value.get("before"), "set before")
    after = _scalar(value.get("after"), "set after")
    if before == after:
        raise ProtocolError("invalid_request", "set change has no effect")
    return {
        "kind": "set",
        "glyph": _text(value.get("glyph"), "set glyph"),
        "layer": _text(value.get("layer"), "set layer"),
        "field": field,
        "before": before,
        "after": after,
    }


def _translate_change(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"kind", "glyph", "layer", "dx", "dy", "beforeHash", "afterHash"}
    _closed(value, allowed, "translate change")
    if set(value) != allowed:
        raise ProtocolError("invalid_request", "translate change fields are incomplete")
    dx = _number(value.get("dx"), "translate dx")
    dy = _number(value.get("dy"), "translate dy")
    if dx == 0 and dy == 0:
        raise ProtocolError("invalid_request", "translate change has no effect")
    return {
        "kind": "translate",
        "glyph": _text(value.get("glyph"), "translate glyph"),
        "layer": _text(value.get("layer"), "translate layer"),
        "dx": dx,
        "dy": dy,
        "beforeHash": _hash(value.get("beforeHash"), "translate beforeHash"),
        "afterHash": _hash(value.get("afterHash"), "translate afterHash"),
    }


def _kerning_change(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"kind", "master", "direction", "left", "right", "before", "after"}
    if set(value) != fields or value.get("direction") not in ("LTR", "RTL", "vertical"):
        raise ProtocolError("invalid_request", "kerning requires exact keys, master, direction and values")
    result = {"kind": "kerning", **{key: _text(value[key], "kerning " + key) for key in ("master", "direction", "left", "right")}}
    for key in ("before", "after"):
        result[key] = None if value[key] is None else _number(value[key], "kerning " + key)
    if result["before"] == result["after"]:
        raise ProtocolError("invalid_request", "kerning change has no effect")
    return result


def _start_node_change(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"kind", "glyph", "layer", "path", "shift", "nodeCount", "beforeHash", "afterHash"}
    if set(value) != fields:
        raise ProtocolError("invalid_request", "start-node fields are incomplete")
    for key, low, high in (("path", 0, 255), ("shift", 1, 4095), ("nodeCount", 2, 4096)):
        v = value[key]
        if isinstance(v, bool) or not isinstance(v, int) or not low <= v <= high:
            raise ProtocolError("invalid_request", "invalid start-node " + key)
    if value["shift"] >= value["nodeCount"]:
        raise ProtocolError("invalid_request", "start-node shift must be less than node count")
    return {"kind": "start_node", "glyph": _text(value["glyph"], "glyph"), "layer": _text(value["layer"], "layer"),
            **{k: value[k] for k in ("path", "shift", "nodeCount")},
            **{k: _hash(value[k], k) for k in ("beforeHash", "afterHash")}}


def validate_patch(value: Any) -> dict[str, Any]:
    patch = _object(value, "patch")
    required = {
        "version",
        "jobId",
        "documentId",
        "sourcePath",
        "sourceHash",
        "generation",
        "changes",
        "summary",
    }
    _closed(patch, required, "patch")
    if set(patch) != required:
        raise ProtocolError("invalid_request", "patch fields are incomplete")
    if patch.get("version") != PATCH_VERSION:
        raise ProtocolError("unsupported_version", "unsupported patch version")
    generation = patch.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise ProtocolError("invalid_request", "generation must be a non-negative integer")
    changes = patch.get("changes")
    if not isinstance(changes, list) or len(changes) > MAX_CHANGES:
        raise ProtocolError(
            "invalid_request", f"changes must contain 0-{MAX_CHANGES} entries"
        )
    from .coordinates import validate as coordinate_change
    from .dimensions import validate_change as dimension_change
    normalized = []
    targets = set()
    outline_changes = 0
    native_contract = None
    native_layer_changes = 0
    native_glyph_changes = 0
    native_font_changes = 0
    native_feature_changes = 0
    for index, raw in enumerate(changes):
        change = _object(raw, f"change {index}")
        kind = change.get("kind")
        from .outline import validate_change as outline_change
        from .native_actions import validate_change as native_action_change
        validator = {"set": _set_change, "translate": _translate_change, "kerning": _kerning_change, "start_node": _start_node_change, "coordinates": coordinate_change, "outline": outline_change, "native_action": native_action_change, "dimension": dimension_change}.get(kind)
        item = validator(change) if validator else None
        if item is None:
            raise ProtocolError("unsupported_change", f"unsupported change kind: {kind}")
        if kind == "outline":
            outline_changes += 1
            if outline_changes > 4096:
                raise ProtocolError("invalid_request", "outline patch exceeds 4,096 layer changes")
        if kind == "dimension":
            if len(changes) > 100 or any(not isinstance(c, Mapping) or c.get("kind") != "dimension" for c in changes):
                raise ProtocolError("invalid_request", "Dimensions patches contain only 0-100 dimension changes")
            target = (kind, item["master"], item["key"])
        elif kind == "kerning":
            target = (kind, item["master"], item["direction"], item["left"], item["right"])
        elif kind == "native_action":
            target = (kind, item["scope"], item.get("glyph"), item.get("layer"), item.get("blockType"), item.get("id"))
            contract = (item["action"], item["scope"], canonical_json(item["arguments"]))
            if native_contract is None:
                native_contract = contract
            elif native_contract != contract:
                raise ProtocolError("invalid_request", "a native_action patch must contain exactly one action")
            if item["scope"] == "layer":
                native_layer_changes += 1
                if native_layer_changes > 4096:
                    raise ProtocolError("invalid_request", "native_action patch exceeds 4,096 layers")
            elif item["scope"] == "glyph":
                native_glyph_changes += 1
                if native_glyph_changes > 100:
                    raise ProtocolError("invalid_request", "native_action patch exceeds 100 glyphs")
            else:
                if item["scope"] == "feature_block":
                    native_feature_changes += 1
                    if native_feature_changes > 100:
                        raise ProtocolError("invalid_request", "native_action patch exceeds 100 feature blocks")
                else:
                    native_font_changes += 1
                    if native_font_changes > 1:
                        raise ProtocolError("invalid_request", "native_action patch contains duplicate font actions")
        else:
            target = (kind, item["glyph"], item["layer"], item.get("field"))
        if target in targets:
            raise ProtocolError("invalid_request", "patch contains a duplicate target")
        targets.add(target)
        normalized.append(item)
    if native_contract is not None and len(normalized) != native_layer_changes + native_glyph_changes + native_font_changes + native_feature_changes:
        raise ProtocolError("invalid_request", "native_action changes cannot be mixed with other change kinds")
    return {
        "version": PATCH_VERSION,
        "jobId": _text(patch.get("jobId"), "jobId", maximum=100),
        "documentId": _text(patch.get("documentId"), "documentId", maximum=100),
        "sourcePath": _text(patch.get("sourcePath"), "sourcePath", maximum=4096),
        "sourceHash": _hash(patch.get("sourceHash"), "sourceHash"),
        "generation": generation,
        "changes": normalized,
        "summary": _text(patch.get("summary"), "summary", maximum=MAX_SUMMARY_LENGTH),
    }


def outline_hash(points: Iterable[tuple[float, float, str]]) -> str:
    normalized = [
        [format(float(x), ".12g"), format(float(y), ".12g"), str(kind)]
        for x, y, kind in points
    ]
    digest = hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest()
    return "sha256:" + digest


def validate_companion_manifest(value: Any) -> dict[str, Any]:
    manifest = _object(value, "companion manifest")
    fields = {"protocol", "id", "version", "capabilities"}
    _closed(manifest, fields, "companion manifest")
    if set(manifest) != fields or manifest.get("protocol") != PROTOCOL_VERSION:
        raise ProtocolError("unsupported_version", "unsupported companion manifest")
    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, list) or len(capabilities) > 100:
        raise ProtocolError("invalid_request", "capabilities must be a bounded list")
    normalized = sorted({_text(item, "capability", maximum=120) for item in capabilities})
    return {
        "protocol": PROTOCOL_VERSION,
        "id": _text(manifest.get("id"), "companion id", maximum=100),
        "version": _text(manifest.get("version"), "companion version", maximum=40),
        "capabilities": normalized,
    }
