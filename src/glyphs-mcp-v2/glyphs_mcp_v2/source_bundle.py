"""Deterministic Glyphs MCP v2 source-bundle planning and normalization.

The native Glyphs exporter remains responsible for serialising outlines.  This
module owns the v2 contract around that renderer: target isolation, OpenType
normalisation, directional kerning preservation, validation, and the
content-addressed manifest used by review and atomic publication.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field
from decimal import Decimal, DivisionByZero, InvalidOperation, ROUND_HALF_EVEN
import hashlib
import io
import json
import math
from pathlib import Path
import plistlib
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping, MutableMapping, Sequence
import xml.etree.ElementTree as ET

from .canonical_tree import CANONICAL_MODEL_SCHEMA_VERSION
from .contracts import API_VERSION
from .semantic import fingerprint_model
from .versions import SERVER_VERSION


BUNDLE_LAYOUT_VERSION = 2
MANIFEST_NAME = "source-manifest.json"
SOURCE_KERNING_LIB_KEY = "cx.ap.GlyphsMCP.sourceKerning.v1"


class SourceBundleError(ValueError):
    """A deterministic export or feature-normalisation failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        target: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = str(code)
        self.target = dict(target or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "target": dict(self.target),
        }


@dataclass(frozen=True)
class ExportPlan:
    """Serializable review contract consumed by one confirmed regeneration."""

    document_id: str
    document_fingerprint: str
    destination: str
    destination_state: Mapping[str, Any]
    overwrite_policy: str
    compatibility_mode: str
    source_fingerprint: str | None = None
    runtime_versions: Mapping[str, Any] = field(default_factory=dict)
    reviewed_bundle_fingerprint: str | None = None
    reviewed_manifest_tree_sha256: str | None = None
    reviewed_manifest_sha256: str | None = None
    layout_version: int = BUNDLE_LAYOUT_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "documentId": self.document_id,
            "documentFingerprint": self.document_fingerprint,
            "destination": self.destination,
            "destinationState": dict(self.destination_state),
            "overwritePolicy": self.overwrite_policy,
            "compatibilityMode": self.compatibility_mode,
            "sourceFingerprint": self.source_fingerprint,
            "runtimeVersions": dict(self.runtime_versions),
            "reviewedBundleFingerprint": self.reviewed_bundle_fingerprint,
            "reviewedManifestTreeSha256": self.reviewed_manifest_tree_sha256,
            "reviewedManifestSha256": self.reviewed_manifest_sha256,
            "bundleLayoutVersion": self.layout_version,
        }


def _items(value: Any, *, key_name: str = "id") -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        result = []
        for key, raw in value.items():
            if not isinstance(raw, Mapping):
                continue
            item = dict(raw)
            item.setdefault(key_name, str(key))
            result.append(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _sequence_strings(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value]
    return []


def _safe_identifier(value: Any, *, prefix: str = "item") -> str:
    text = re.sub(r"[^A-Za-z0-9_.]", "_", str(value or ""))
    if not text or not (text[0].isalpha() or text[0] == "_"):
        text = "{}_{}".format(prefix, text)
    digest = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:8]
    return "{}_{}".format(text, digest)


def _canonical_glyph_name(value: Any, aliases: Mapping[str, str]) -> str:
    text = str(value or "")
    if text in aliases:
        return aliases[text]
    if text.startswith("glyph_") and text[6:] in aliases:
        return aliases[text[6:]]
    if text.startswith("glyph:") and text[6:] in aliases:
        return aliases[text[6:]]
    raise SourceBundleError(
        "kerning_key_unresolved",
        "Kerning references an unknown glyph key: {}".format(text),
        target={"key": text},
    )


def _glyph_inventory(model: Mapping[str, Any]) -> tuple[list[str], dict[str, str], dict[str, Mapping[str, Any]]]:
    glyph_records = _items(model.get("glyphs", {}), key_name="name")
    glyphs: dict[str, Mapping[str, Any]] = {}
    aliases: dict[str, str] = {}
    order = [str(value) for value in model.get("glyphOrder", ()) if str(value)]
    for glyph in glyph_records:
        name = str(glyph.get("name") or "")
        if not name:
            continue
        glyphs[name] = glyph
        for alias in (name, glyph.get("id"), "glyph_{}".format(name), "glyph:{}".format(name)):
            if alias not in (None, ""):
                aliases[str(alias)] = name
    ordered = [name for name in order if name in glyphs]
    ordered.extend(sorted(set(glyphs) - set(ordered)))
    return ordered, aliases, glyphs


def _split_code_and_literals(code: str) -> list[tuple[bool, str]]:
    """Split feature text into transformable code and inert comments/strings."""

    result: list[tuple[bool, str]] = []
    start = 0
    index = 0
    while index < len(code):
        character = code[index]
        if character == "#":
            if start < index:
                result.append((True, code[start:index]))
            end = code.find("\n", index)
            if end < 0:
                end = len(code)
            else:
                end += 1
            result.append((False, code[index:end]))
            index = end
            start = end
            continue
        if character == '"':
            if start < index:
                result.append((True, code[start:index]))
            end = index + 1
            escaped = False
            while end < len(code):
                current = code[end]
                if current == '"' and not escaped:
                    end += 1
                    break
                escaped = current == "\\" and not escaped
                if current != "\\":
                    escaped = False
                end += 1
            if end > len(code) or code[end - 1 : end] != '"':
                raise SourceBundleError(
                    "feature_string_unterminated",
                    "OpenType feature code contains an unterminated string.",
                )
            result.append((False, code[index:end]))
            index = end
            start = end
            continue
        index += 1
    if start < len(code):
        result.append((True, code[start:]))
    return result


_CONDITIONAL_RE = re.compile(
    r"^[ \t]*#(?P<directive>ifdef|ifndef|else|endif)(?:[ \t]+(?P<name>[^\s#]+))?[ \t]*(?:#.*)?$"
)


def select_variable_blocks(code: str, *, variable: bool) -> str:
    """Evaluate Glyphs' VARIABLE preprocessor without regex block deletion."""

    output: list[str] = []
    stack: list[dict[str, Any]] = []
    active = True
    for line_number, line in enumerate(str(code).splitlines(keepends=True), 1):
        match = _CONDITIONAL_RE.match(line.rstrip("\r\n"))
        if match is None:
            if active:
                output.append(line)
            continue
        directive = match.group("directive")
        name = match.group("name")
        if directive in {"ifdef", "ifndef"}:
            if name != "VARIABLE":
                raise SourceBundleError(
                    "feature_conditional_unsupported",
                    "Only #ifdef VARIABLE and #ifndef VARIABLE are supported.",
                    target={"line": line_number, "name": name},
                )
            condition = variable if directive == "ifdef" else not variable
            stack.append(
                {
                    "parent": active,
                    "condition": condition,
                    "else": False,
                    "line": line_number,
                }
            )
            active = active and condition
            continue
        if not stack:
            raise SourceBundleError(
                "feature_conditional_malformed",
                "{} has no matching #ifdef VARIABLE.".format("#" + directive),
                target={"line": line_number},
            )
        frame = stack[-1]
        if directive == "else":
            raise SourceBundleError(
                "feature_conditional_malformed",
                "#else is not supported; use separate #ifdef/#ifndef VARIABLE blocks.",
                target={"line": line_number},
            )
        if name is not None:
            raise SourceBundleError(
                "feature_conditional_malformed",
                "#endif must not contain an identifier.",
                target={"line": line_number},
            )
        stack.pop()
        active = bool(frame["parent"])
    if stack:
        raise SourceBundleError(
            "feature_conditional_malformed",
            "A #ifdef VARIABLE block is missing #endif.",
            target={"line": stack[-1]["line"]},
        )
    return "".join(output)


_ARITHMETIC_TOKEN_RE = re.compile(
    r"\$[A-Za-z_][A-Za-z0-9_.-]*|(?:\d+(?:\.\d*)?|\.\d+)|[()+\-*/]|\s+"
)


def _decimal_expression(expression: str, values: Mapping[str, Any]) -> int:
    references: list[str] = []

    def replace_reference(match: re.Match[str]) -> str:
        name = match.group(0)[1:]
        references.append(name)
        return "__number_{}".format(len(references) - 1)

    translated = re.sub(r"\$[A-Za-z_][A-Za-z0-9_.-]*", replace_reference, expression)
    try:
        tree = ast.parse(translated.strip(), mode="eval")
    except SyntaxError as exc:
        raise SourceBundleError(
            "number_expression_malformed",
            "Malformed Number Value arithmetic: {}".format(expression.strip()),
        ) from exc

    def evaluate(node: ast.AST) -> Decimal:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name) and node.id.startswith("__number_"):
            try:
                name = references[int(node.id.rsplit("_", 1)[1])]
                raw = values[name]
            except (IndexError, KeyError, ValueError) as exc:
                requested = references[int(node.id.rsplit("_", 1)[1])]
                raise SourceBundleError(
                    "number_value_unresolved",
                    "Unknown Number Value: ${}".format(requested),
                    target={"name": requested},
                ) from exc
            try:
                return Decimal(str(raw))
            except InvalidOperation as exc:
                raise SourceBundleError(
                    "number_value_invalid",
                    "Number Value ${} is not finite numeric data.".format(name),
                    target={"name": name},
                ) from exc
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left = evaluate(node.left)
            right = evaluate(node.right)
            try:
                if isinstance(node.op, ast.Add):
                    return left + right
                if isinstance(node.op, ast.Sub):
                    return left - right
                if isinstance(node.op, ast.Mult):
                    return left * right
                return left / right
            except (DivisionByZero, ZeroDivisionError) as exc:
                raise SourceBundleError(
                    "number_expression_division_by_zero",
                    "Number Value arithmetic divides by zero.",
                ) from exc
        raise SourceBundleError(
            "number_expression_unsupported",
            "Number Value arithmetic supports only literals, references, parentheses, and + - * /.",
        )

    result = evaluate(tree)
    if not result.is_finite():
        raise SourceBundleError(
            "number_value_invalid",
            "Number Value arithmetic produced a non-finite result.",
        )
    # Glyphs 4 resolves Number Value feature metrics to integer design units
    # with ties-to-even rounding. The committed native-export parity fixture
    # covers positive and negative 0.5 and 2.5 boundaries.
    integral = result.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    return int(integral)


def _arithmetic_regions(segment: str) -> list[tuple[int, int, str]]:
    """Find maximal parseable arithmetic regions containing a dollar token."""

    tokens: list[tuple[int, int, str]] = []
    index = 0
    while index < len(segment):
        match = _ARITHMETIC_TOKEN_RE.match(segment, index)
        if match is None:
            index += 1
            continue
        tokens.append((match.start(), match.end(), match.group(0)))
        index = match.end()
    regions: list[tuple[int, int, str]] = []
    used_until = -1
    for token_index, (start, _end, token) in enumerate(tokens):
        if not token.startswith("$") or start < used_until:
            continue
        component_start = token_index
        component_end = token_index + 1
        while component_start > 0 and tokens[component_start - 1][1] == tokens[component_start][0]:
            component_start -= 1
        while component_end < len(tokens) and tokens[component_end - 1][1] == tokens[component_end][0]:
            component_end += 1
        candidates: list[tuple[int, int, str]] = []
        for left in range(component_start, token_index + 1):
            for right in range(token_index + 1, component_end + 1):
                candidate = segment[tokens[left][0] : tokens[right - 1][1]]
                if "$" not in candidate:
                    continue
                translated = re.sub(r"\$[A-Za-z_][A-Za-z0-9_.-]*", "1", candidate)
                try:
                    parsed = ast.parse(translated.strip(), mode="eval")
                except SyntaxError:
                    continue
                if any(
                    not isinstance(
                        node,
                        (
                            ast.Expression,
                            ast.Constant,
                            ast.UnaryOp,
                            ast.BinOp,
                            ast.UAdd,
                            ast.USub,
                            ast.Add,
                            ast.Sub,
                            ast.Mult,
                            ast.Div,
                            ast.Load,
                        ),
                    )
                    for node in ast.walk(parsed)
                ):
                    continue
                candidates.append((tokens[left][0], tokens[right - 1][1], candidate))
        if not candidates:
            raise SourceBundleError(
                "unsupported_dollar_token",
                "A dollar token is not a valid Number Value expression.",
                target={"offset": start},
            )
        selected = max(candidates, key=lambda value: (value[1] - value[0], -value[0]))
        selected_start, selected_end, _selected_expression = selected
        while selected_start < selected_end and segment[selected_start].isspace():
            selected_start += 1
        while selected_end > selected_start and segment[selected_end - 1].isspace():
            selected_end -= 1
        selected = (
            selected_start,
            selected_end,
            segment[selected_start:selected_end],
        )
        regions.append(selected)
        used_until = selected[1]
    return regions


def resolve_number_values(
    code: str,
    *,
    values_by_master: Mapping[str, Mapping[str, Any]],
    master_id: str | None,
    variable_locations: Mapping[str, str] | None = None,
    default_master_id: str | None = None,
) -> str:
    """Resolve every active Number Value token to standards-compliant FEA."""

    variable_locations = dict(variable_locations or {})
    result: list[str] = []
    for transformable, segment in _split_code_and_literals(str(code)):
        if not transformable or "$" not in segment:
            result.append(segment)
            continue
        def expand_braced(match: re.Match[str]) -> str:
            expression = match.group(1).strip()
            if not expression:
                raise SourceBundleError(
                    "number_expression_malformed",
                    "A ${...} Number Value expression cannot be empty.",
                )
            # Number Value arithmetic uses bare names inside braces.  Turn
            # every identifier into the same internal $name representation;
            # property/predicate tokens retain ':'/'[' and are rejected by
            # the arithmetic grammar below.
            return re.sub(
                r"(?<![A-Za-z0-9_.-])([A-Za-z_][A-Za-z0-9_.-]*)",
                lambda value: "$" + value.group(1),
                expression,
            )

        original_segment = segment
        braced_count = original_segment.count("${")
        matched_braces = len(re.findall(r"\$\{[^{}]*\}", original_segment))
        segment = re.sub(r"\$\{([^{}]*)\}", expand_braced, original_segment)
        if segment.count("${") != 0 or braced_count != matched_braces:
            raise SourceBundleError(
                "number_expression_malformed",
                "Number Value arithmetic contains unbalanced braces.",
            )
        regions = _arithmetic_regions(segment)
        cursor = 0
        for start, end, expression in regions:
            result.append(segment[cursor:start])
            if master_id is not None:
                values = values_by_master.get(master_id)
                if values is None:
                    raise SourceBundleError(
                        "number_master_unresolved",
                        "No Number Values were captured for master {}.".format(master_id),
                        target={"masterId": master_id},
                    )
                replacement = str(_decimal_expression(expression, values))
            else:
                ordered_ids = [value for value in variable_locations if value in values_by_master]
                if not ordered_ids:
                    plain_values = [
                        _decimal_expression(expression, values)
                        for values in values_by_master.values()
                    ]
                    if not plain_values:
                        raise SourceBundleError(
                            "number_master_unresolved",
                            "Number Value resolution requires at least one master.",
                        )
                    if len(set(plain_values)) != 1:
                        raise SourceBundleError(
                            "variable_location_unavailable",
                            "A varying Number Value requires defined design axes.",
                            target={"expression": expression.strip()},
                        )
                    result.append(str(plain_values[0]))
                    cursor = end
                    continue
                parts = []
                for candidate_id in ordered_ids:
                    value = _decimal_expression(expression, values_by_master[candidate_id])
                    parts.append("{}:{}".format(variable_locations[candidate_id], value))
                replacement = "({})".format(" ".join(parts))
            result.append(replacement)
            cursor = end
        result.append(segment[cursor:])
    normalized = "".join(result)
    for transformable, segment in _split_code_and_literals(normalized):
        if transformable and "$" in segment:
            offset = segment.index("$")
            raise SourceBundleError(
                "unsupported_dollar_token",
                "Only captured Number Value references are permitted in exported feature code.",
                target={"offset": offset},
            )
    return normalized


def _number_values(model: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    definitions = _items(model.get("numbers", ()))
    names: dict[str, str] = {}
    for definition in definitions:
        definition_id = str(definition.get("id") or "")
        name = str(definition.get("name") or "")
        if not definition_id or not name:
            continue
        if name in names and names[name] != definition_id:
            raise SourceBundleError(
                "number_name_collision",
                "Number Value names must be unique for deterministic export: {}".format(name),
                target={"name": name},
            )
        names[name] = definition_id
    result: dict[str, dict[str, Any]] = {}
    for master in _items(model.get("masters", ())):
        master_id = str(master.get("id") or "")
        by_id = {
            str(item.get("id") or ""): item.get("value")
            for item in _items(master.get("numberValues", ()))
        }
        values: dict[str, Any] = {}
        for name, definition_id in names.items():
            if definition_id in by_id:
                values[name] = by_id[definition_id]
                values[definition_id] = by_id[definition_id]
        result[master_id] = values
    return result


def _parameter_values(owner: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for parameter in _items(owner.get("customParameters", ()), key_name="name"):
        if parameter.get("disabled"):
            continue
        name = str(parameter.get("name") or "")
        if name:
            # Glyphs resolves duplicate custom parameters in document order;
            # the final enabled value is authoritative.
            values[name] = parameter.get("value")
    return values


def _enabled_parameter(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def _effective_master_sources(model: Mapping[str, Any]) -> dict[str, str]:
    """Resolve Glyphs' Link Metrics parameters for kerning source lookup."""

    masters = _items(model.get("masters", ()))
    ids = [str(master.get("id") or "") for master in masters]
    if not ids:
        return {}
    names: dict[str, list[str]] = {}
    for master, master_id in zip(masters, ids):
        names.setdefault(str(master.get("name") or ""), []).append(master_id)
    direct: dict[str, str] = {}
    first_id = ids[0]
    for master, master_id in zip(masters, ids):
        parameters = _parameter_values(master)
        named = parameters.get("Link Metrics With Master")
        if named not in (None, ""):
            requested = str(named)
            if requested in ids:
                direct[master_id] = requested
                continue
            matches = names.get(requested, ())
            if len(matches) != 1:
                raise SourceBundleError(
                    "linked_master_unresolved",
                    "Link Metrics With Master must identify one unique master.",
                    target={"masterId": master_id, "requestedMaster": requested},
                )
            direct[master_id] = matches[0]
        elif _enabled_parameter(parameters.get("Link Metrics With First Master")):
            direct[master_id] = first_id
        else:
            direct[master_id] = master_id

    resolved: dict[str, str] = {}

    def resolve(master_id: str, path: tuple[str, ...]) -> str:
        if master_id in resolved:
            return resolved[master_id]
        if master_id in path:
            raise SourceBundleError(
                "linked_master_cycle",
                "Linked metrics masters form a cycle.",
                target={"masterIds": list(path + (master_id,))},
            )
        target = direct.get(master_id, master_id)
        if target == master_id:
            resolved[master_id] = master_id
        else:
            resolved[master_id] = resolve(target, path + (master_id,))
        return resolved[master_id]

    for master_id in ids:
        resolve(master_id, ())
    return resolved


def _fea_decimal(value: Any, *, target: Mapping[str, Any]) -> str:
    if isinstance(value, bool):
        raise SourceBundleError(
            "variable_location_invalid",
            "Variable design locations must contain finite numeric coordinates.",
            target=target,
        )
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SourceBundleError(
            "variable_location_invalid",
            "Variable design locations must contain finite numeric coordinates.",
            target=target,
        ) from exc
    if not decimal.is_finite():
        raise SourceBundleError(
            "variable_location_invalid",
            "Variable design locations must contain finite numeric coordinates.",
            target=target,
        )
    text = format(decimal, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _master_locations(
    model: Mapping[str, Any], *, syntax: str
) -> tuple[dict[str, str], str | None, list[str]]:
    if syntax not in {"inline", "named"}:
        raise ValueError("location syntax must be inline or named")
    masters = _items(model.get("masters", ()))
    axes = [str(axis.get("tag") or "") for axis in _items(model.get("axes", ()))]
    locations: dict[str, str] = {}
    declarations: list[str] = []
    default_id: str | None = None
    defaults = {
        str(axis.get("tag") or ""): axis.get("default")
        for axis in _items(model.get("axes", ()))
    }
    seen_locations: dict[str, str] = {}
    for master in masters:
        master_id = str(master.get("id") or "")
        coordinates = {
            str(item.get("tag") or ""): item.get("internal")
            for item in _items(master.get("axes", ()), key_name="tag")
        }
        coordinate_text = [
            _fea_decimal(
                coordinates.get(tag, 0),
                target={"masterId": master_id, "axisTag": tag},
            )
            for tag in axes
        ]
        default_text = [
            _fea_decimal(
                defaults.get(tag, 0),
                target={"axisTag": tag, "kind": "axisDefault"},
            )
            for tag in axes
        ]
        if axes and coordinate_text == default_text:
            default_id = master_id
        if axes:
            inline_location = ",".join(
                "{}={}".format(tag, value)
                for tag, value in zip(axes, coordinate_text)
            )
            previous_master = seen_locations.get(inline_location)
            if previous_master is not None:
                raise SourceBundleError(
                    "variable_location_collision",
                    "Variable masters must occupy unique design locations.",
                    target={
                        "location": inline_location,
                        "masterIds": [previous_master, master_id],
                    },
                )
            seen_locations[inline_location] = master_id
            if syntax == "inline":
                # Pinned FontTools 4.54.1 does not parse AFDKO locationDef.
                # UFO-local sources therefore use the equivalent expanded
                # scalar syntax consumed by fontmake.
                locations[master_id] = inline_location
            else:
                name = "@GMCP_location_{}".format(
                    _safe_identifier(master_id, prefix="master")
                )
                declaration_location = ", ".join(
                    "{}={} d".format(tag, value)
                    for tag, value in zip(axes, coordinate_text)
                )
                declarations.append(
                    "locationDef {} {};".format(declaration_location, name)
                )
                locations[master_id] = name
    if default_id is None and masters:
        default_id = str(masters[0].get("id") or "")
    return locations, default_id, declarations


def _variable_target_eligibility(model: Mapping[str, Any]) -> tuple[bool, str | None]:
    masters = _items(model.get("masters", ()))
    axes = _items(model.get("axes", ()))
    if len(masters) < 2:
        return False, "requires_multiple_masters"
    if not axes:
        return False, "requires_axis"
    tags = [str(axis.get("tag") or "") for axis in axes]
    if any(not re.match(r"^[A-Za-z0-9]{4}$", tag) for tag in tags):
        return False, "invalid_axis_tag"
    if len(set(tags)) != len(tags):
        return False, "duplicate_axis_tag"
    locations: list[tuple[Decimal, ...]] = []
    for master in masters:
        coordinates = {
            str(item.get("tag") or ""): item.get("internal")
            for item in _items(master.get("axes", ()), key_name="tag")
        }
        location: list[Decimal] = []
        for tag in tags:
            try:
                value = Decimal(str(coordinates[tag]))
            except (KeyError, InvalidOperation):
                return False, "incomplete_master_location"
            if not value.is_finite():
                return False, "nonfinite_master_location"
            location.append(value)
        locations.append(tuple(location))
    if len(set(locations)) != len(locations):
        return False, "duplicate_master_location"
    return True, None


def normalize_feature_code(
    code: str,
    *,
    variable: bool,
    values_by_master: Mapping[str, Mapping[str, Any]],
    master_id: str | None = None,
    variable_locations: Mapping[str, str] | None = None,
    default_master_id: str | None = None,
) -> str:
    selected = select_variable_blocks(str(code), variable=variable)
    return resolve_number_values(
        selected,
        values_by_master=values_by_master,
        master_id=master_id,
        variable_locations=variable_locations,
        default_master_id=default_master_id,
    )


_RESERVED_LOOKUP_RE = re.compile(r"\blookup\s+GMCP_[A-Za-z0-9_.-]*", re.IGNORECASE)
_CONDITION_RE = re.compile(r"^\s*condition\s+(?P<ranges>.+?)\s*;\s*(?:#.*)?$")
_SIMPLE_SUB_RE = re.compile(
    r"^\s*sub\s+(?P<source>[A-Za-z_.][A-Za-z0-9_.-]*)\s+by\s+"
    r"(?P<replacement>[A-Za-z_.][A-Za-z0-9_.-]*)\s*;\s*(?:#.*)?$"
)
_NUMBER_PATTERN = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
_TWO_SIDED_CONDITION_RE = re.compile(
    r"^\s*(?P<minimum>{number})\s*<\s*(?P<tag>[A-Za-z0-9]{{4}})\s*<\s*"
    r"(?P<maximum>{number})\s*$".format(number=_NUMBER_PATTERN)
)
_LOWER_CONDITION_RE = re.compile(
    r"^\s*(?P<minimum>{number})\s*<\s*(?P<tag>[A-Za-z0-9]{{4}})\s*$".format(
        number=_NUMBER_PATTERN
    )
)
_UPPER_CONDITION_RE = re.compile(
    r"^\s*(?P<tag>[A-Za-z0-9]{{4}})\s*<\s*(?P<maximum>{number})\s*$".format(
        number=_NUMBER_PATTERN
    )
)


def _reject_reserved_lookups(code: str, *, target: Mapping[str, Any]) -> None:
    match = _RESERVED_LOOKUP_RE.search(str(code))
    if match is not None:
        raise SourceBundleError(
            "reserved_lookup_collision",
            "User feature code cannot declare or reference GMCP_ reserved lookups.",
            target={**dict(target), "lookup": match.group(0).split()[-1]},
        )


def _condition_axis_bounds(model: Mapping[str, Any]) -> dict[str, tuple[Decimal, Decimal]]:
    tags = [str(axis.get("tag") or "") for axis in _items(model.get("axes", ())) ]
    values: dict[str, list[Decimal]] = {tag: [] for tag in tags if tag}
    invalid: set[str] = set()
    for master in _items(model.get("masters", ())):
        coordinates = {
            str(item.get("tag") or ""): item.get("internal")
            for item in _items(master.get("axes", ()), key_name="tag")
        }
        for tag in values:
            try:
                value = Decimal(str(coordinates[tag]))
            except (KeyError, InvalidOperation):
                invalid.add(tag)
                continue
            if not value.is_finite():
                invalid.add(tag)
                continue
            values[tag].append(value)
    return {
        tag: (min(coordinates), max(coordinates))
        for tag, coordinates in values.items()
        if coordinates and tag not in invalid
    }


def _decimal_public(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _parse_condition_ranges(
    raw: str, *, axis_bounds: Mapping[str, tuple[Decimal, Decimal]]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for expression in str(raw).split(","):
        match = (
            _TWO_SIDED_CONDITION_RE.match(expression)
            or _LOWER_CONDITION_RE.match(expression)
            or _UPPER_CONDITION_RE.match(expression)
        )
        if match is None:
            raise SourceBundleError(
                "condition_syntax_unsupported",
                "Condition ranges must use lower < axisTag < upper or a one-sided form.",
                target={"condition": expression.strip()},
            )
        tag = match.group("tag")
        if tag not in axis_bounds:
            raise SourceBundleError(
                "condition_axis_unresolved",
                "Conditional substitution references an unknown design axis.",
                target={"axisTag": tag},
            )
        if tag in seen:
            raise SourceBundleError(
                "condition_axis_duplicate",
                "One condition cannot constrain the same axis twice.",
                target={"axisTag": tag},
            )
        seen.add(tag)
        axis_minimum, axis_maximum = axis_bounds[tag]
        minimum = Decimal(match.group("minimum")) if match.groupdict().get("minimum") else axis_minimum
        maximum = Decimal(match.group("maximum")) if match.groupdict().get("maximum") else axis_maximum
        if not minimum.is_finite() or not maximum.is_finite() or minimum > maximum:
            raise SourceBundleError(
                "condition_range_invalid",
                "Conditional substitution ranges must be finite and ordered.",
                target={"axisTag": tag},
            )
        result.append(
            {
                "axisTag": tag,
                "minimum": _decimal_public(minimum),
                "maximum": _decimal_public(maximum),
            }
        )
    if not result:
        raise SourceBundleError(
            "condition_syntax_unsupported", "A condition must define at least one axis range."
        )
    return result


def _extract_condition_substitutions(
    code: str,
    *,
    variable: bool,
    axis_bounds: Mapping[str, tuple[Decimal, Decimal]],
    aliases: Mapping[str, str],
    target: Mapping[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    lines = str(code).splitlines()
    has_condition = any(_CONDITION_RE.match(line) for line in lines)
    if not has_condition:
        return code, []
    if not variable:
        raise SourceBundleError(
            "condition_static_unsupported",
            "Glyphs condition substitutions must be inside a VARIABLE-only block.",
            target=target,
        )
    output: list[str] = []
    rules: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line_number, line in enumerate(lines, 1):
        condition = _CONDITION_RE.match(line)
        if condition is not None:
            current = {
                "conditions": _parse_condition_ranges(
                    condition.group("ranges"), axis_bounds=axis_bounds
                ),
                "substitutions": [],
                "source": {**dict(target), "line": line_number},
            }
            rules.append(current)
            continue
        if current is None:
            output.append(line)
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        substitution = _SIMPLE_SUB_RE.match(line)
        if substitution is None:
            raise SourceBundleError(
                "condition_rule_unsupported",
                "Conditional Designspace rules support only simple one-to-one glyph substitutions.",
                target={**dict(target), "line": line_number},
            )
        source = _canonical_glyph_name(substitution.group("source"), aliases)
        replacement = _canonical_glyph_name(
            substitution.group("replacement"), aliases
        )
        current["substitutions"].append(
            {"source": source, "replacement": replacement}
        )
    for rule in rules:
        if not rule["substitutions"]:
            raise SourceBundleError(
                "condition_rule_empty",
                "Every conditional range must contain at least one simple substitution.",
                target=rule["source"],
            )
    return "\n".join(output).strip(), rules


_MMK_RE = re.compile(r"^@MMK_(?P<side>[LRBT])_(?P<name>.+)$")
_CLASS_RE = re.compile(r"^@[A-Za-z_][A-Za-z0-9_.]*$")
_SCRIPT_TAGS = {
    "arabic": "arab",
    "armenian": "armn",
    "cyrillic": "cyrl",
    "devanagari": "deva",
    "georgian": "geor",
    "greek": "grek",
    "hebrew": "hebr",
    "latin": "latn",
    "syriac": "syrc",
    "thaana": "thaa",
}
_RTL_SCRIPTS = {"arab", "hebr", "syrc", "thaa", "nkoo", "adlm", "rohg"}


def _fea_glyph(name: str) -> str:
    if not re.match(r"^[A-Za-z_.][A-Za-z0-9_.-]*$", name):
        raise SourceBundleError(
            "feature_glyph_name_invalid",
            "Glyph name cannot be represented in AFDKO source: {}".format(name),
            target={"glyphName": name},
        )
    return "\\" + name


def _integer_metric(value: Any, *, target: Mapping[str, Any]) -> int:
    if isinstance(value, bool):
        raise SourceBundleError(
            "kerning_value_invalid", "Kerning values must be finite integers.", target=target
        )
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise SourceBundleError(
            "kerning_value_invalid", "Kerning values must be finite integers.", target=target
        ) from exc
    if not math.isfinite(numeric) or not numeric.is_integer():
        raise SourceBundleError(
            "kerning_value_invalid", "Kerning values must be finite integers.", target=target
        )
    integer = int(numeric)
    if not -32768 <= integer <= 32767:
        raise SourceBundleError(
            "kerning_value_out_of_range",
            "Kerning values must fit an OpenType signed 16-bit metric.",
            target={**dict(target), "value": integer},
        )
    return integer


def _group_members(
    glyph_order: Sequence[str], glyphs: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, list[str]]]:
    attributes = {
        "L": "rightKerningGroup",
        "R": "leftKerningGroup",
        "B": "bottomKerningGroup",
        "T": "topKerningGroup",
    }
    result: dict[str, dict[str, list[str]]] = {side: {} for side in attributes}
    for name in glyph_order:
        glyph = glyphs[name]
        if glyph.get("export") is False:
            continue
        for side, attribute in attributes.items():
            group = str(glyph.get(attribute) or "")
            if group:
                result[side].setdefault(group, []).append(name)
    return result


def _feature_class_name(raw: str) -> str:
    if _CLASS_RE.match(raw):
        return raw
    return "@GMCP_{}".format(_safe_identifier(raw.lstrip("@"), prefix="class"))


def _class_for_key(
    key: str,
    *,
    group_members: Mapping[str, Mapping[str, Sequence[str]]],
    class_definitions: MutableMapping[str, tuple[str, ...]],
    class_map: MutableMapping[str, str],
    vertical_position: int | None = None,
) -> str:
    match = _MMK_RE.match(key)
    if match is None:
        raise SourceBundleError(
            "kerning_class_unsupported",
            "Unsupported kerning class key: {}".format(key),
            target={"key": key},
        )
    side = match.group("side")
    group_name = match.group("name")
    if vertical_position is not None and side in {"L", "R"}:
        # Older sources may retain horizontal key prefixes in kerningVertical.
        # Position is authoritative there: first/top uses the bottom group and
        # second/bottom uses the top group.
        side = "B" if vertical_position == 0 else "T"
    members = tuple(group_members.get(side, {}).get(group_name, ()))
    if not members:
        raise SourceBundleError(
            "kerning_class_empty",
            "Referenced kerning class has no exporting glyphs: {}".format(key),
            target={"key": key, "groupName": group_name},
        )
    class_name = _feature_class_name(key)
    existing = class_definitions.get(class_name)
    if existing is not None and existing != members:
        raise SourceBundleError(
            "feature_class_collision",
            "Feature class {} has conflicting memberships.".format(class_name),
            target={"className": class_name},
        )
    class_definitions[class_name] = members
    class_map[key] = class_name
    return class_name


def _pair_operand(
    key: Any,
    *,
    aliases: Mapping[str, str],
    group_members: Mapping[str, Mapping[str, Sequence[str]]],
    class_definitions: MutableMapping[str, tuple[str, ...]],
    class_map: MutableMapping[str, str],
    vertical_position: int | None = None,
) -> tuple[str, tuple[str, ...]]:
    text = str(key or "")
    if text.startswith("@"):
        class_name = _class_for_key(
            text,
            group_members=group_members,
            class_definitions=class_definitions,
            class_map=class_map,
            vertical_position=vertical_position,
        )
        return class_name, class_definitions[class_name]
    name = _canonical_glyph_name(text, aliases)
    return _fea_glyph(name), (name,)


def _metric_source(
    values: Mapping[str, Any],
    *,
    master_ids: Sequence[str],
    master_id: str | None,
    locations: Mapping[str, str],
    default_master_id: str | None,
    target: Mapping[str, Any],
) -> tuple[str, tuple[int, ...]]:
    vector = tuple(
        _integer_metric(values.get(candidate, 0), target={**dict(target), "masterId": candidate})
        for candidate in master_ids
    )
    if master_id is not None:
        if master_id not in master_ids:
            raise SourceBundleError(
                "kerning_master_unresolved",
                "Kerning export requested an unknown master: {}".format(master_id),
                target={"masterId": master_id},
            )
        return str(vector[master_ids.index(master_id)]), vector
    if not master_ids:
        return "0", vector
    if not locations:
        if len(set(vector)) != 1:
            raise SourceBundleError(
                "variable_location_unavailable",
                "Varying kerning requires defined design axes.",
                target=target,
            )
        return str(vector[0]), vector
    values_by_location: dict[str, int] = {}
    ordered_locations: list[str] = []
    for candidate, value in zip(master_ids, vector):
        location = locations.get(candidate)
        if not location:
            raise SourceBundleError(
                "variable_location_unavailable",
                "Every variable kerning master requires a complete design location.",
                target={**dict(target), "masterId": candidate},
            )
        previous = values_by_location.get(location)
        if previous is not None and previous != value:
            raise SourceBundleError(
                "variable_location_collision",
                "Masters at one design location assign different kerning values.",
                target={
                    **dict(target),
                    "location": location,
                    "values": [previous, value],
                },
            )
        if location not in values_by_location:
            ordered_locations.append(location)
        values_by_location[location] = value
    parts = [
        "{}:{}".format(location, values_by_location[location])
        for location in ordered_locations
    ]
    return "({})".format(" ".join(parts)), vector


@dataclass(frozen=True)
class _PairRule:
    direction: str
    first: str
    second: str
    first_members: tuple[str, ...]
    second_members: tuple[str, ...]
    metric: str
    vector: tuple[int, ...]
    specificity: int
    scripts: tuple[str, ...]


@dataclass(frozen=True)
class _RawPairRule:
    left: str
    right: str
    first_members: tuple[str, ...]
    second_members: tuple[str, ...]
    value: int
    specificity: int


def _script_tags_for_members(
    members: Iterable[str], glyphs: Mapping[str, Mapping[str, Any]], *, direction: str
) -> tuple[str, ...]:
    member_names = tuple(name for name in members if name in glyphs)
    tags = {
        _SCRIPT_TAGS.get(str(glyphs[name].get("script") or "").lower(), "")
        for name in member_names
    }
    tags.discard("")
    if direction == "rtl":
        tags = {tag for tag in tags if tag in _RTL_SCRIPTS}
        if not tags:
            raise SourceBundleError(
                "rtl_script_unresolved",
                "RTL kerning requires at least one mapped canonical RTL script; it cannot fall back to DFLT.",
                target={"direction": direction, "glyphNames": list(member_names)},
            )
    elif direction == "ltr":
        tags = {tag for tag in tags if tag not in _RTL_SCRIPTS}
    return tuple(sorted(tags or {"DFLT"}))


def _domain_rules(
    model: Mapping[str, Any],
    *,
    direction: str,
    aliases: Mapping[str, str],
    glyphs: Mapping[str, Mapping[str, Any]],
    group_members: Mapping[str, Mapping[str, Sequence[str]]],
    class_definitions: MutableMapping[str, tuple[str, ...]],
    class_map: MutableMapping[str, str],
    master_ids: Sequence[str],
    master_id: str | None,
    locations: Mapping[str, str],
    default_master_id: str | None,
) -> list[_PairRule]:
    kerning = model.get("kerning", {})
    domain = kerning.get(direction, {}) if isinstance(kerning, Mapping) else {}
    if not isinstance(domain, Mapping):
        return []
    effective_sources = _effective_master_sources(model)
    by_master: dict[str, list[_RawPairRule]] = {candidate: [] for candidate in master_ids}
    concrete_topology: set[tuple[str, str]] = set()
    for candidate in master_ids:
        source_master = effective_sources.get(candidate, candidate)
        lefts = domain.get(source_master, {})
        if not isinstance(lefts, Mapping):
            continue
        for left, rights in sorted(lefts.items(), key=lambda item: str(item[0])):
            if not isinstance(rights, Mapping):
                continue
            for right, raw_value in sorted(rights.items(), key=lambda item: str(item[0])):
                left_text, right_text = str(left), str(right)
                _first, first_members = _pair_operand(
                    left_text,
                    aliases=aliases,
                    group_members=group_members,
                    class_definitions=class_definitions,
                    class_map=class_map,
                    vertical_position=0 if direction == "vertical" else None,
                )
                _second, second_members = _pair_operand(
                    right_text,
                    aliases=aliases,
                    group_members=group_members,
                    class_definitions=class_definitions,
                    class_map=class_map,
                    vertical_position=1 if direction == "vertical" else None,
                )
                value = _integer_metric(
                    raw_value,
                    target={
                        "direction": direction,
                        "masterId": candidate,
                        "effectiveMasterId": source_master,
                        "left": left_text,
                        "right": right_text,
                    },
                )
                specificity = int(not left_text.startswith("@")) + int(
                    not right_text.startswith("@")
                )
                raw_rule = _RawPairRule(
                    left_text,
                    right_text,
                    first_members,
                    second_members,
                    value,
                    specificity,
                )
                by_master[candidate].append(raw_rule)
                for first_name in first_members:
                    for second_name in second_members:
                        concrete_topology.add((first_name, second_name))
                        if len(concrete_topology) > 1_000_000:
                            raise SourceBundleError(
                                "kerning_expansion_limit",
                                "Kerning expansion exceeds one million concrete pairs.",
                                target={"direction": direction},
                            )

    resolved: dict[str, dict[tuple[str, str], int]] = {}
    for candidate in master_ids:
        candidates: dict[tuple[str, str], list[_RawPairRule]] = {}
        for raw_rule in by_master[candidate]:
            for first_name in raw_rule.first_members:
                for second_name in raw_rule.second_members:
                    candidates.setdefault((first_name, second_name), []).append(raw_rule)
        effective: dict[tuple[str, str], int] = {}
        for pair in concrete_topology:
            matches = candidates.get(pair, ())
            if not matches:
                effective[pair] = 0
                continue
            highest = max(rule.specificity for rule in matches)
            winners = [rule for rule in matches if rule.specificity == highest]
            winner_values = {rule.value for rule in winners}
            if len(winner_values) != 1:
                raise SourceBundleError(
                    "kerning_specificity_collision",
                    "Equal-specificity kerning rules assign conflicting values.",
                    target={
                        "direction": direction,
                        "masterId": candidate,
                        "first": pair[0],
                        "second": pair[1],
                        "rules": [
                            {"left": rule.left, "right": rule.right, "value": rule.value}
                            for rule in winners
                        ],
                    },
                )
            # Presence, including an explicit zero, wins at this specificity.
            effective[pair] = next(iter(winner_values))
        resolved[candidate] = effective

    rules: list[_PairRule] = []
    for first_name, second_name in sorted(concrete_topology):
        values = {
            candidate: resolved[candidate].get((first_name, second_name), 0)
            for candidate in master_ids
        }
        metric, vector = _metric_source(
            values,
            master_ids=master_ids,
            master_id=master_id,
            locations=locations,
            default_master_id=default_master_id,
            target={
                "direction": direction,
                "first": first_name,
                "second": second_name,
            },
        )
        scripts = _script_tags_for_members(
            (first_name, second_name), glyphs, direction=direction
        )
        rules.append(
            _PairRule(
                direction,
                _fea_glyph(first_name),
                _fea_glyph(second_name),
                (first_name,),
                (second_name,),
                metric,
                vector,
                2,
                scripts,
            )
        )
    return sorted(
        rules,
        key=lambda rule: (-rule.specificity, rule.first, rule.second, rule.vector),
    )


def _deduplicate_directional_rules(rules: Sequence[_PairRule]) -> list[_PairRule]:
    """Prevent one concrete pair from applying in both horizontal domains."""

    seen: dict[tuple[str, str, str], tuple[str, tuple[int, ...]]] = {}
    output: list[_PairRule] = []
    for rule in rules:
        if rule.direction not in {"ltr", "rtl"}:
            output.append(rule)
            continue
        retained_scripts: list[str] = []
        for script in rule.scripts:
            keys = [
                (script, first, second)
                for first in rule.first_members
                for second in rule.second_members
            ]
            overlaps = [key for key in keys if key in seen]
            if overlaps:
                previous_direction, previous_vector = seen[overlaps[0]]
                if previous_direction != rule.direction and previous_vector != rule.vector:
                    raise SourceBundleError(
                        "directional_pair_collision",
                        "LTR and RTL kerning assign different values to the same script-scoped pair.",
                        target={
                            "script": script,
                            "first": overlaps[0][1],
                            "second": overlaps[0][2],
                            "ltrOrRtl": [previous_direction, rule.direction],
                        },
                    )
                # Identical cross-domain values are emitted once. LTR wins
                # because domains are assembled in stable ltr/rtl order.
                continue
            retained_scripts.append(script)
            for key in keys:
                seen[key] = (rule.direction, rule.vector)
        if retained_scripts:
            output.append(
                _PairRule(
                    rule.direction,
                    rule.first,
                    rule.second,
                    rule.first_members,
                    rule.second_members,
                    rule.metric,
                    rule.vector,
                    rule.specificity,
                    tuple(retained_scripts),
                )
            )
    return output


def _context_tokens(raw: str) -> tuple[list[str], int]:
    tokens = re.findall(r"\[[^\]]*\]|[^\s]+", str(raw or ""))
    if tokens.count("*") != 1:
        raise SourceBundleError(
            "context_key_malformed",
            "Context kerning keys must contain exactly one * boundary.",
            target={"rawContextKey": raw},
        )
    boundary = tokens.index("*")
    sequence = tokens[:boundary] + tokens[boundary + 1 :]
    if len(sequence) < 3 or boundary < 1 or boundary >= len(sequence):
        raise SourceBundleError(
            "context_key_malformed",
            "Context kerning requires at least three tokens and an internal boundary.",
            target={"rawContextKey": raw},
        )
    return sequence, boundary


def _context_operand(
    token: str,
    *,
    aliases: Mapping[str, str],
    user_classes: Mapping[str, tuple[str, ...]],
    group_members: Mapping[str, Mapping[str, Sequence[str]]],
    class_definitions: MutableMapping[str, tuple[str, ...]],
    class_map: MutableMapping[str, str],
) -> tuple[str, tuple[str, ...]]:
    if token.startswith("[") and token.endswith("]"):
        raw_members = [value for value in token[1:-1].split() if value]
        members = tuple(_canonical_glyph_name(value, aliases) for value in raw_members)
        if not members:
            raise SourceBundleError("context_class_empty", "A context bracket class is empty.")
        return "[{}]".format(" ".join(_fea_glyph(value) for value in members)), members
    if token.startswith("@MMK_"):
        class_name = _class_for_key(
            token,
            group_members=group_members,
            class_definitions=class_definitions,
            class_map=class_map,
        )
        return class_name, class_definitions[class_name]
    if token.startswith("@"):
        class_name = _feature_class_name(token)
        members = user_classes.get(class_name)
        if members is None:
            raise SourceBundleError(
                "context_class_unresolved",
                "Context kerning references an unknown feature class: {}".format(token),
                target={"className": token},
            )
        return class_name, members
    name = _canonical_glyph_name(token, aliases)
    return _fea_glyph(name), (name,)


@dataclass(frozen=True)
class _ContextRule:
    operands: tuple[str, ...]
    members: tuple[tuple[str, ...], ...]
    metrics: tuple[tuple[int, str, tuple[int, ...]], ...]
    scripts: tuple[str, ...]


def _context_rules(
    model: Mapping[str, Any],
    *,
    aliases: Mapping[str, str],
    glyphs: Mapping[str, Mapping[str, Any]],
    user_classes: Mapping[str, tuple[str, ...]],
    group_members: Mapping[str, Mapping[str, Sequence[str]]],
    class_definitions: MutableMapping[str, tuple[str, ...]],
    class_map: MutableMapping[str, str],
    master_ids: Sequence[str],
    master_id: str | None,
    locations: Mapping[str, str],
    default_master_id: str | None,
) -> list[_ContextRule]:
    kerning = model.get("kerning", {})
    contexts = kerning.get("context", {}) if isinstance(kerning, Mapping) else {}
    if not isinstance(contexts, Mapping):
        return []
    effective_sources = _effective_master_sources(model)
    grouped: dict[tuple[str, ...], dict[int, tuple[str, tuple[int, ...]]]] = {}
    member_map: dict[tuple[str, ...], tuple[tuple[str, ...], ...]] = {}
    seen_contexts: list[
        tuple[tuple[str, ...], tuple[tuple[str, ...], ...], int, str]
    ] = []
    for raw_key, raw_values in sorted(contexts.items(), key=lambda item: str(item[0])):
        if not isinstance(raw_values, Mapping):
            raise SourceBundleError(
                "context_value_invalid",
                "Context kerning values must be keyed by master ID.",
                target={"rawContextKey": str(raw_key)},
            )
        sequence, boundary = _context_tokens(str(raw_key))
        resolved = [
            _context_operand(
                token,
                aliases=aliases,
                user_classes=user_classes,
                group_members=group_members,
                class_definitions=class_definitions,
                class_map=class_map,
            )
            for token in sequence
        ]
        operands = tuple(value[0] for value in resolved)
        members = tuple(value[1] for value in resolved)
        effective_values = {
            candidate: raw_values.get(
                effective_sources.get(candidate, candidate), 0
            )
            for candidate in master_ids
        }
        metric, vector = _metric_source(
            effective_values,
            master_ids=master_ids,
            master_id=master_id,
            locations=locations,
            default_master_id=default_master_id,
            target={"rawContextKey": str(raw_key), "boundaryIndex": boundary},
        )
        for previous_operands, previous_members, previous_boundary, previous_key in seen_contexts:
            if previous_operands == operands:
                continue
            previous_positions = {
                index - previous_boundary: set(values)
                for index, values in enumerate(previous_members)
            }
            current_positions = {
                index - boundary: set(values)
                for index, values in enumerate(members)
            }
            shared_positions = previous_positions.keys() & current_positions.keys()
            if shared_positions and all(
                previous_positions[position].intersection(current_positions[position])
                for position in shared_positions
            ):
                raise SourceBundleError(
                    "context_collision",
                    "Overlapping contextual kerning rules target the same boundary and would both apply.",
                    target={
                        "boundaryIndex": boundary,
                        "rawContextKey": str(raw_key),
                        "reference": previous_key,
                    },
                )
        seen_contexts.append((operands, members, boundary, str(raw_key)))
        previous = grouped.setdefault(operands, {}).get(boundary)
        if previous is not None and previous[1] != vector:
            raise SourceBundleError(
                "context_collision",
                "Equivalent context keys assign different values to one boundary.",
                target={"sequence": list(sequence), "boundaryIndex": boundary},
            )
        grouped[operands][boundary] = (metric, vector)
        member_map[operands] = members
    result = []
    for operands in sorted(grouped):
        members = member_map[operands]
        flattened = tuple(name for values in members for name in values)
        direction = "rtl" if any(
            _SCRIPT_TAGS.get(str(glyphs[name].get("script") or "").lower(), "") in _RTL_SCRIPTS
            for name in flattened
            if name in glyphs
        ) else "ltr"
        result.append(
            _ContextRule(
                operands,
                members,
                tuple(
                    (boundary, value[0], value[1])
                    for boundary, value in sorted(grouped[operands].items())
                ),
                _script_tags_for_members(flattened, glyphs, direction=direction),
            )
        )
    return result


def _simple_class_members(
    code: str, aliases: Mapping[str, str]
) -> tuple[str, ...] | None:
    stripped = str(code or "").strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        stripped = stripped[1:-1].strip()
    if any(character in stripped for character in "'=$:{}"):
        return None
    result: list[str] = []
    for token in stripped.split():
        if token.startswith("#"):
            break
        try:
            result.append(_canonical_glyph_name(token.lstrip("\\"), aliases))
        except SourceBundleError:
            return None
    return tuple(result) if result else None


def _generated_lookup_sources(
    pair_rules: Sequence[_PairRule], context_rules: Sequence[_ContextRule]
) -> tuple[list[str], dict[str, list[tuple[str, str]]], set[str]]:
    lookup_blocks: list[str] = []
    references: dict[str, list[tuple[str, str]]] = {"kern": [], "vkrn": []}
    scripts: set[str] = set()
    for direction in ("ltr", "rtl", "vertical"):
        direction_rules = [rule for rule in pair_rules if rule.direction == direction]
        direction_scripts = sorted({script for rule in direction_rules for script in rule.scripts})
        for script in direction_scripts:
            selected = [rule for rule in direction_rules if script in rule.scripts]
            if not selected:
                continue
            tag = "vkrn" if direction == "vertical" else "kern"
            lookup_name = "GMCP_{}_{}_{}".format(
                tag, direction, _safe_identifier(script, prefix="script")
            )
            lines = ["lookup {} {{".format(lookup_name)]
            for rule in selected:
                value_record = (
                    "<0 0 0 {}>".format(rule.metric)
                    if direction == "vertical"
                    else "<0 0 {} 0>".format(rule.metric)
                )
                lines.append(
                    "  pos {} {} {};".format(rule.first, rule.second, value_record)
                )
            lines.append("}} {};".format(lookup_name))
            lookup_blocks.append("\n".join(lines))
            references[tag].append((script, lookup_name))
            scripts.add(script)

    context_scripts = sorted(
        {script for rule in context_rules for script in rule.scripts}
    )
    for script in context_scripts:
        selected_contexts = [rule for rule in context_rules if script in rule.scripts]
        lookup_name = "GMCP_kern_context_{}".format(
            _safe_identifier(script, prefix="script")
        )
        lines = ["lookup {} {{".format(lookup_name)]
        for rule in selected_contexts:
            adjustments = {boundary - 1: metric for boundary, metric, _vector in rule.metrics}
            pieces = []
            for index, operand in enumerate(rule.operands):
                metric = adjustments.get(index)
                if metric is None:
                    pieces.append(operand)
                else:
                    pieces.append("{}' <0 0 {} 0>".format(operand, metric))
            lines.append("  pos {};".format(" ".join(pieces)))
        lines.append("}} {};".format(lookup_name))
        lookup_blocks.append("\n".join(lines))
        references["kern"].append((script, lookup_name))
        scripts.add(script)
    return lookup_blocks, references, scripts


def _lookup_reference_code(references: Sequence[tuple[str, str]]) -> str:
    by_script: dict[str, list[str]] = {}
    for script, lookup in references:
        by_script.setdefault(script, []).append(lookup)
    lines = []
    for script in sorted(by_script, key=lambda value: (value != "DFLT", value)):
        lines.append("  script {};".format(script))
        lines.append("  language dflt;")
        lines.extend("  lookup {};".format(name) for name in by_script[script])
    return "\n".join(lines)


def _insert_generated_references(
    code: str, generated: str, *, automatic: bool
) -> str:
    lines = str(code).splitlines()
    has_automatic_marker = any(
        line.strip() == "# Automatic Code" for line in lines
    )
    if automatic and generated and not has_automatic_marker:
        return generated
    if automatic and not has_automatic_marker:
        return str(code).strip()
    output: list[str] = []
    inserted = False
    for line in lines:
        if line.strip() == "# Automatic Code":
            if not inserted and generated:
                output.extend(generated.splitlines())
                inserted = True
            continue
        output.append(line)
    if generated and not inserted:
        if output and output[-1].strip():
            output.append("")
        output.extend(generated.splitlines())
    return "\n".join(output).strip()


def build_feature_source(
    model: Mapping[str, Any],
    *,
    target_kind: str,
    master_id: str | None = None,
    location_syntax: str = "named",
) -> tuple[str, dict[str, Any]]:
    """Build one self-contained AFDKO source for a static or variable target.

    A variable target without ``master_id`` is the shared Designspace source
    and retains standards-compliant variable metrics.  Supplying ``master_id``
    keeps VARIABLE branch selection and Designspace-rule extraction, but
    materializes every metric at that source location so the emitted UFO can be
    compiled independently by the pinned toolchain.
    """

    if target_kind not in {"static", "variable"}:
        raise ValueError("target_kind must be static or variable")
    if location_syntax not in {"inline", "named"}:
        raise ValueError("location_syntax must be inline or named")
    variable = target_kind == "variable"
    masters = _items(model.get("masters", ()))
    master_ids = [str(master.get("id") or "") for master in masters]
    if master_id is not None and master_id not in master_ids:
        raise SourceBundleError(
            "kerning_master_unresolved",
            "Feature generation references an unknown master ID.",
            target={"masterId": master_id},
        )
    if not variable and master_id is None:
        raise SourceBundleError(
            "kerning_master_unresolved",
            "Static feature generation requires an explicit master ID.",
            target={"masterId": master_id},
        )
    locations, default_master_id, location_declarations = _master_locations(
        model, syntax=location_syntax if variable else "inline"
    )
    if master_id is not None:
        location_declarations = []
    values_by_master = _number_values(model)
    glyph_order, aliases, glyphs = _glyph_inventory(model)
    axis_bounds = _condition_axis_bounds(model)
    groups = _group_members(glyph_order, glyphs)
    class_definitions: dict[str, tuple[str, ...]] = {}
    class_map: dict[str, str] = {}
    normalized_user_classes: list[tuple[str, str]] = []
    user_class_members: dict[str, tuple[str, ...]] = {}

    normalize_arguments = {
        "variable": variable,
        "values_by_master": values_by_master,
        "master_id": master_id,
        "variable_locations": locations,
        "default_master_id": default_master_id,
    }
    for item in _items(model.get("classes", ()), key_name="name"):
        if item.get("disabled"):
            continue
        raw_name = "@" + str(item.get("name") or item.get("tag") or "").lstrip("@")
        name = _feature_class_name(raw_name)
        code = normalize_feature_code(str(item.get("code") or ""), **normalize_arguments)
        _reject_reserved_lookups(code, target={"kind": "class", "name": name})
        if any(_CONDITION_RE.match(line) for line in code.splitlines()):
            raise SourceBundleError(
                "condition_rule_unsupported",
                "Conditional substitutions are supported only in feature code.",
                target={"kind": "class", "name": name},
            )
        normalized_user_classes.append((name, code.strip().strip("[]")))
        members = _simple_class_members(code, aliases)
        if members is not None:
            existing = class_definitions.get(name)
            if existing is not None and existing != members:
                raise SourceBundleError(
                    "feature_class_collision",
                    "Feature class {} has conflicting memberships.".format(name),
                    target={"className": name},
                )
            class_definitions[name] = members
            user_class_members[name] = members

    pair_rules: list[_PairRule] = []
    for direction in ("ltr", "rtl", "vertical"):
        pair_rules.extend(
            _domain_rules(
                model,
                direction=direction,
                aliases=aliases,
                glyphs=glyphs,
                group_members=groups,
                class_definitions=class_definitions,
                class_map=class_map,
                master_ids=master_ids,
                master_id=master_id,
                locations=locations,
                default_master_id=default_master_id,
            )
        )
    pair_rules = _deduplicate_directional_rules(pair_rules)
    contexts = _context_rules(
        model,
        aliases=aliases,
        glyphs=glyphs,
        user_classes=user_class_members,
        group_members=groups,
        class_definitions=class_definitions,
        class_map=class_map,
        master_ids=master_ids,
        master_id=master_id,
        locations=locations,
        default_master_id=default_master_id,
    )
    lookups, references, generated_scripts = _generated_lookup_sources(
        pair_rules, contexts
    )

    prefixes = []
    for item in _items(model.get("featurePrefixes", ()), key_name="name"):
        if item.get("disabled"):
            continue
        prefix_name = str(item.get("name") or "")
        normalized_prefix = normalize_feature_code(
            str(item.get("code") or ""), **normalize_arguments
        ).strip()
        _reject_reserved_lookups(
            normalized_prefix, target={"kind": "prefix", "name": prefix_name}
        )
        if any(_CONDITION_RE.match(line) for line in normalized_prefix.splitlines()):
            raise SourceBundleError(
                "condition_rule_unsupported",
                "Conditional substitutions are supported only in feature code.",
                target={"kind": "prefix", "name": prefix_name},
            )
        prefixes.append(normalized_prefix)
    prefix_source = "\n\n".join(value for value in prefixes if value)
    declared_scripts = {
        match.group(1)
        for match in re.finditer(
            r"\blanguagesystem\s+([A-Za-z0-9]{4})\s+[A-Za-z0-9]{4}\s*;",
            prefix_source,
        )
    }
    language_systems = []
    for script in sorted(generated_scripts | {"DFLT"}, key=lambda value: (value != "DFLT", value)):
        if script not in declared_scripts:
            language_systems.append("languagesystem {} dflt;".format(script))

    features_by_tag: dict[str, list[tuple[str, bool]]] = {}
    feature_order: list[str] = []
    condition_rules: list[dict[str, Any]] = []
    for item in _items(model.get("features", ()), key_name="name"):
        if item.get("disabled"):
            continue
        tag = str(item.get("tag") or item.get("name") or "")
        if not re.match(r"^[A-Za-z0-9]{4}$", tag):
            raise SourceBundleError(
                "feature_tag_invalid",
                "OpenType feature tags must be exactly four alphanumeric characters.",
                target={"tag": tag},
            )
        if tag not in features_by_tag:
            feature_order.append(tag)
        normalized = normalize_feature_code(
            str(item.get("code") or ""), **normalize_arguments
        )
        _reject_reserved_lookups(
            normalized, target={"kind": "feature", "tag": tag}
        )
        normalized, extracted_conditions = _extract_condition_substitutions(
            normalized,
            variable=variable,
            axis_bounds=axis_bounds,
            aliases=aliases,
            target={"kind": "feature", "tag": tag},
        )
        condition_rules.extend(extracted_conditions)
        features_by_tag.setdefault(tag, []).append(
            (normalized, bool(item.get("automatic")))
        )
    for required in ("kern", "vkrn"):
        if references[required] and required not in features_by_tag:
            feature_order.append(required)
            features_by_tag[required] = [("", True)]

    feature_blocks = []
    for tag in feature_order:
        entries = features_by_tag[tag]
        contents = []
        for entry_code, automatic in entries:
            generated = _lookup_reference_code(references[tag]) if tag in references else ""
            contents.append(
                _insert_generated_references(
                    entry_code,
                    generated if not any(generated in prior for prior in contents) else "",
                    automatic=automatic,
                )
            )
        content = "\n\n".join(value for value in contents if value)
        if not content.strip():
            continue
        indented = "\n".join("  " + line if line else "" for line in content.splitlines())
        feature_blocks.append("feature {} {{\n{}\n}} {};".format(tag, indented, tag))

    generated_class_sources = []
    user_names = {name for name, _code in normalized_user_classes}
    for name, members in sorted(class_definitions.items()):
        if name in user_names:
            if name in class_map.values() and user_class_members.get(name) != members:
                raise SourceBundleError(
                    "feature_class_collision",
                    "A referenced kerning class collides with an opaque or different user class.",
                    target={"className": name},
                )
            continue
        generated_class_sources.append(
            "{} = [{}];".format(name, " ".join(_fea_glyph(member) for member in members))
        )
    user_class_sources = [
        "{} = [{}];".format(name, code) for name, code in normalized_user_classes
    ]

    sections = [
        "# Glyphs MCP source bundle layout v{}".format(BUNDLE_LAYOUT_VERSION),
        "\n".join(location_declarations),
        "\n".join(language_systems),
        prefix_source,
        "\n".join(user_class_sources + generated_class_sources),
        "\n\n".join(lookups),
        "\n\n".join(feature_blocks),
    ]
    source = "\n\n".join(value for value in sections if value.strip()).rstrip() + "\n"
    if re.search(r"(?m)^\s*#(?:ifn?def|else|endif)\b", source):
        raise SourceBundleError(
            "feature_conditional_unresolved",
            "Exported feature code retained a Glyphs conditional directive.",
        )
    for transformable, segment in _split_code_and_literals(source):
        if transformable and "$" in segment:
            raise SourceBundleError(
                "unsupported_dollar_token",
                "Exported feature code retained a dollar token.",
            )
    return source, {
        "targetKind": target_kind,
        "masterId": master_id,
        "kerningRuleCount": len(pair_rules),
        "contextRuleCount": len(contexts),
        "classMap": dict(sorted(class_map.items())),
        "scripts": sorted(generated_scripts),
        "conditionRules": condition_rules,
    }


def _load_plist(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    try:
        with path.open("rb") as handle:
            return plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise SourceBundleError(
            "ufo_plist_invalid",
            "UFO contains an invalid property list: {}".format(path.name),
            target={"path": str(path)},
        ) from exc


def _write_plist(path: Path, value: Any) -> None:
    try:
        payload = plistlib.dumps(value, fmt=plistlib.FMT_XML, sort_keys=True)
        path.write_bytes(payload)
    except (OSError, TypeError, ValueError) as exc:
        raise SourceBundleError(
            "ufo_plist_write_failed",
            "Could not write deterministic UFO data: {}".format(path.name),
            target={"path": str(path)},
        ) from exc


def _ufo_groups(model: Mapping[str, Any]) -> dict[str, list[str]]:
    glyph_order, _aliases, glyphs = _glyph_inventory(model)
    members = _group_members(glyph_order, glyphs)
    result: dict[str, list[str]] = {}
    # UFO side 1 is the first/left glyph and therefore uses Glyphs'
    # rightKerningGroup. UFO side 2 uses leftKerningGroup.
    for group, names in sorted(members["L"].items()):
        result["public.kern1.{}".format(group)] = list(names)
    for group, names in sorted(members["R"].items()):
        result["public.kern2.{}".format(group)] = list(names)
    return result


def _ufo_kerning(model: Mapping[str, Any], master_id: str) -> dict[str, dict[str, int]]:
    _glyph_order, aliases, _glyphs = _glyph_inventory(model)
    kerning = model.get("kerning", {})
    ltr = kerning.get("ltr", {}) if isinstance(kerning, Mapping) else {}
    effective_master_id = _effective_master_sources(model).get(master_id, master_id)
    domain = ltr.get(effective_master_id, {}) if isinstance(ltr, Mapping) else {}
    if not isinstance(domain, Mapping):
        return {}
    result: dict[str, dict[str, int]] = {}
    for raw_left, rights in sorted(domain.items(), key=lambda item: str(item[0])):
        if not isinstance(rights, Mapping):
            continue
        left = str(raw_left)
        if left.startswith("@"):
            match = _MMK_RE.match(left)
            if match is None or match.group("side") != "L":
                raise SourceBundleError(
                    "ufo_ltr_class_side_invalid",
                    "LTR first-side classes must use @MMK_L_*.",
                    target={"masterId": master_id, "key": left},
                )
            left = "public.kern1.{}".format(match.group("name"))
        else:
            left = _canonical_glyph_name(left, aliases)
        for raw_right, value in sorted(rights.items(), key=lambda item: str(item[0])):
            right = str(raw_right)
            if right.startswith("@"):
                match = _MMK_RE.match(right)
                if match is None or match.group("side") != "R":
                    raise SourceBundleError(
                        "ufo_ltr_class_side_invalid",
                        "LTR second-side classes must use @MMK_R_*.",
                        target={"masterId": master_id, "key": right},
                    )
                right = "public.kern2.{}".format(match.group("name"))
            else:
                right = _canonical_glyph_name(right, aliases)
            result.setdefault(left, {})[right] = _integer_metric(
                value,
                target={"masterId": master_id, "left": left, "right": right},
            )
    return result


def _plist_safe(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        return {str(key): _plist_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plist_safe(item) for item in value]
    if isinstance(value, (str, bytes, bool, int, float)):
        return value
    return str(value)


def rewrite_ufo_source(
    ufo_path: Path,
    *,
    model: Mapping[str, Any],
    master_id: str,
    feature_source: str,
    feature_metadata: Mapping[str, Any],
) -> None:
    if not ufo_path.is_dir():
        raise SourceBundleError(
            "ufo_missing", "Native export did not create the expected UFO.", target={"path": str(ufo_path)}
        )
    groups_path = ufo_path / "groups.plist"
    groups = _load_plist(groups_path, {})
    if not isinstance(groups, dict):
        raise SourceBundleError("ufo_groups_invalid", "UFO groups.plist must be a dictionary.")
    groups = {
        str(key): value
        for key, value in groups.items()
        if not str(key).startswith(("public.kern1.", "public.kern2."))
    }
    groups.update(_ufo_groups(model))
    _write_plist(groups_path, groups)
    _write_plist(ufo_path / "kerning.plist", _ufo_kerning(model, master_id))

    lib_path = ufo_path / "lib.plist"
    lib = _load_plist(lib_path, {})
    if not isinstance(lib, dict):
        raise SourceBundleError("ufo_lib_invalid", "UFO lib.plist must be a dictionary.")
    kerning = model.get("kerning", {})
    lib[SOURCE_KERNING_LIB_KEY] = _plist_safe(
        {
            "schemaVersion": 1,
            "masterId": master_id,
            "featureAuthority": "features.fea",
            "domains": kerning if isinstance(kerning, Mapping) else {},
            "classMap": dict(feature_metadata.get("classMap") or {}),
        }
    )
    _write_plist(lib_path, lib)
    (ufo_path / "features.fea").write_text(feature_source, encoding="utf-8", newline="\n")


def _write_designspace_condition_rules(
    path: Path, rules: Sequence[Mapping[str, Any]]
) -> None:
    if not rules:
        # Static Designspaces can contain native rules unrelated to Glyphs
        # feature conditions. An empty generated set is not authorization to
        # erase them.
        return
    try:
        from fontTools.designspaceLib import DesignSpaceDocument, RuleDescriptor

        document = DesignSpaceDocument.fromfile(path)
        axes = {str(axis.tag): axis for axis in document.axes}
        generated = []
        for index, rule_data in enumerate(rules, 1):
            rule = RuleDescriptor()
            rule.name = "GMCP Condition {:04d}".format(index)
            condition_set = []
            for condition in rule_data.get("conditions", ()):
                tag = str(condition.get("axisTag") or "")
                axis = axes.get(tag)
                if axis is None:
                    raise SourceBundleError(
                        "condition_axis_unresolved",
                        "The variable Designspace omitted a conditional substitution axis.",
                        target={"path": str(path), "axisTag": tag},
                    )
                condition_set.append(
                    {
                        "name": axis.name,
                        "minimum": float(condition.get("minimum")),
                        "maximum": float(condition.get("maximum")),
                    }
                )
            rule.conditionSets = [condition_set]
            rule.subs = [
                (str(item.get("source") or ""), str(item.get("replacement") or ""))
                for item in rule_data.get("substitutions", ())
            ]
            generated.append(rule)

        def signature(rule: Any) -> tuple[Any, ...]:
            condition_sets = tuple(
                sorted(
                    tuple(
                        sorted(
                            (
                                str(condition.get("name") or ""),
                                "" if condition.get("minimum") is None else str(condition.get("minimum")),
                                "" if condition.get("maximum") is None else str(condition.get("maximum")),
                            )
                            for condition in condition_set
                        )
                    )
                    for condition_set in (rule.conditionSets or ())
                )
            )
            substitutions = tuple(
                (str(source), str(replacement))
                for source, replacement in (rule.subs or ())
            )
            return condition_sets, substitutions

        generated_signatures = {signature(rule) for rule in generated}
        generated_substitutions = {
            tuple((str(source), str(replacement)) for source, replacement in rule.subs)
            for rule in generated
        }
        generated_names = {str(rule.name or "") for rule in generated}
        preserved = []
        for existing in document.rules:
            existing_signature = signature(existing)
            if existing_signature in generated_signatures:
                continue
            existing_substitutions = tuple(
                (str(source), str(replacement))
                for source, replacement in (existing.subs or ())
            )
            if (
                str(existing.name or "") in generated_names
                or existing_substitutions in generated_substitutions
            ):
                raise SourceBundleError(
                    "condition_rule_collision",
                    "A native Designspace rule conflicts with a canonical feature condition.",
                    target={"path": str(path), "name": str(existing.name or "")},
                )
            preserved.append(existing)
        document.rules = preserved + generated
        document.rulesProcessingLast = True
        document.write(path)
    except SourceBundleError:
        raise
    except Exception as exc:
        raise SourceBundleError(
            "condition_designspace_write_failed",
            "Could not write validated conditional substitutions to Designspace.",
            target={"path": str(path)},
        ) from exc


def _file_records(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    casefolded: dict[str, str] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        folded = relative.casefold()
        previous = casefolded.get(folded)
        if previous is not None and previous != relative:
            raise SourceBundleError(
                "bundle_path_collision",
                "Bundle paths collide on a case-insensitive filesystem.",
                target={"paths": [previous, relative]},
            )
        casefolded[folded] = relative
        if path.is_symlink():
            raise SourceBundleError(
                "bundle_symlink_unsupported",
                "Source bundles must not contain symbolic links.",
                target={"path": relative},
            )
        if path.is_dir():
            continue
        if not path.is_file():
            raise SourceBundleError(
                "bundle_object_unsupported",
                "Source bundles may contain only directories and regular files.",
                target={"path": relative},
            )
        if relative == MANIFEST_NAME:
            continue
        payload = path.read_bytes()
        records.append(
            {
                "path": relative,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return records


def _records_digest(records: Sequence[Mapping[str, Any]]) -> str:
    canonical = json.dumps(list(records), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _bundle_fingerprint(root: Path) -> str:
    records = _file_records(root)
    manifest_path = root / MANIFEST_NAME
    if manifest_path.is_file():
        payload = manifest_path.read_bytes()
        records = [
            *records,
            {
                "path": MANIFEST_NAME,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        ]
    return _records_digest(sorted(records, key=lambda item: str(item["path"])))


def write_source_manifest(
    root: Path,
    *,
    document_fingerprint: str,
    source_fingerprint: str | None = None,
    compatibility_mode: str,
    runtime_versions: Mapping[str, Any],
    targets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    records = _file_records(root)
    manifest = {
        "schemaVersion": 1,
        "bundleLayoutVersion": BUNDLE_LAYOUT_VERSION,
        "canonicalModelSchemaVersion": CANONICAL_MODEL_SCHEMA_VERSION,
        "documentFingerprint": str(document_fingerprint),
        "compatibilityMode": compatibility_mode,
        "versions": {
            "application": str(runtime_versions.get("application", "Glyphs")),
            "applicationVersion": str(
                runtime_versions.get("applicationVersion", "unknown")
            ),
            "applicationBuild": str(runtime_versions.get("buildNumber", "unknown")),
            "glyphsMcpServerVersion": str(SERVER_VERSION),
            "mcpApiVersion": str(API_VERSION),
        },
        "targets": [dict(target) for target in targets],
        "files": records,
        "fileCount": len(records),
        "treeSha256": _records_digest(records),
        "manifest": {"path": MANIFEST_NAME, "selfHashExcluded": True},
    }
    if source_fingerprint:
        manifest["sourceFingerprint"] = str(source_fingerprint)
    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ).encode("utf-8") + b"\n"
    (root / MANIFEST_NAME).write_bytes(payload)
    return manifest


def _manifest_artifact(root: Path) -> dict[str, Any]:
    payload = (root / MANIFEST_NAME).read_bytes()
    return {
        "manifestSize": len(payload),
        "manifestSha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
    }


_LOCATION_DEF_RE = re.compile(
    r"^\s*locationDef\s+(?P<location>.+?)\s+"
    r"(?P<name>@GMCP_location_[A-Za-z_][A-Za-z0-9_.]*)\s*;\s*(?:#.*)?$"
)
_LOCATION_DEF_COORDINATE_RE = re.compile(
    r"^\s*(?P<tag>[A-Za-z0-9]{{4}})\s*=\s*"
    r"(?P<value>{})\s+d\s*$".format(_NUMBER_PATTERN)
)


def _expand_location_definitions_for_fealib(text: str) -> str:
    """Translate generated AFDKO named locations for pinned feaLib.

    AFDKO 1.27 defines ``locationDef`` and named references, while the pinned
    FontTools 4.54.1 parser rejects the declaration keyword.  The shared
    variable source remains standards-facing; validation and UFO-local build
    sources use this lossless expansion to the equivalent inline locations.
    """

    definitions: dict[str, str] = {}
    output: list[str] = []
    for line in str(text).splitlines(keepends=True):
        if not re.match(r"^\s*locationDef\b", line):
            output.append(line)
            continue
        match = _LOCATION_DEF_RE.match(line.rstrip("\r\n"))
        if match is None:
            raise SourceBundleError(
                "feature_location_definition_invalid",
                "Generated locationDef syntax is not supported by the pinned build bridge.",
            )
        name = match.group("name")
        if name in definitions:
            raise SourceBundleError(
                "feature_location_definition_invalid",
                "Generated locationDef names must be unique.",
                target={"name": name},
            )
        coordinates: list[str] = []
        observed_tags: set[str] = set()
        for raw_coordinate in match.group("location").split(","):
            coordinate = _LOCATION_DEF_COORDINATE_RE.match(raw_coordinate)
            if coordinate is None:
                raise SourceBundleError(
                    "feature_location_definition_invalid",
                    "Generated locationDef coordinates must use four-character tags and design-space units.",
                    target={"name": name, "location": raw_coordinate.strip()},
                )
            tag = coordinate.group("tag")
            if tag in observed_tags:
                raise SourceBundleError(
                    "feature_location_definition_invalid",
                    "Generated locationDef coordinates must not repeat an axis.",
                    target={"name": name, "axisTag": tag},
                )
            observed_tags.add(tag)
            value = _fea_decimal(
                coordinate.group("value"),
                target={"name": name, "axisTag": tag},
            )
            coordinates.append("{}={}".format(tag, value))
        if not coordinates:
            raise SourceBundleError(
                "feature_location_definition_invalid",
                "Generated locationDef declarations require at least one coordinate.",
                target={"name": name},
            )
        definitions[name] = ",".join(coordinates)
        output.append("\n" if line.endswith(("\n", "\r")) else "")

    expanded = "".join(output)
    for name, location in definitions.items():
        expanded = re.sub(
            re.escape(name) + r"(?=\s*:)",
            location,
            expanded,
        )
    unresolved = re.search(r"@GMCP_location_[A-Za-z_][A-Za-z0-9_.]*\s*:", expanded)
    if unresolved is not None:
        raise SourceBundleError(
            "feature_location_reference_unresolved",
            "Generated variable scalar references an undeclared location.",
            target={"name": unresolved.group(0).rstrip().rstrip(":")},
        )
    return expanded


def _validate_feature_file(
    path: Path,
    glyph_names: Sequence[str],
    *,
    model: Mapping[str, Any],
    variable: bool,
) -> None:
    text = path.read_text(encoding="utf-8")
    try:
        from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
        from fontTools.feaLib.parser import Parser
        from fontTools.ttLib import TTFont, newTable
        from fontTools.ttLib.tables._f_v_a_r import Axis

        parser_source = _expand_location_definitions_for_fealib(text)
        Parser(
            io.StringIO(parser_source),
            glyphNames=tuple(glyph_names),
            followIncludes=True,
        ).parse()

        # Parsing does not enforce every builder invariant. In particular, a
        # named lookup that mixes GSUB and GPOS statements parses successfully
        # but fails later in fontmake. Compile every assembled source against a
        # minimal font so review and confirmation reject that class of failure.
        compile_font = TTFont(recalcBBoxes=False, recalcTimestamp=False)
        compile_font.setGlyphOrder(list(glyph_names))
        if variable:
            bounds = _condition_axis_bounds(model)
            fvar = newTable("fvar")
            fvar.axes = []
            fvar.instances = []
            for index, axis_model in enumerate(_items(model.get("axes", ()))):
                tag = str(axis_model.get("tag") or "")
                if tag not in bounds:
                    raise SourceBundleError(
                        "variable_location_unavailable",
                        "Variable feature compilation requires complete axis bounds.",
                        target={"axisTag": tag},
                    )
                minimum, maximum = bounds[tag]
                try:
                    default = Decimal(str(axis_model.get("default", minimum)))
                except InvalidOperation as exc:
                    raise SourceBundleError(
                        "variable_location_unavailable",
                        "Variable feature compilation requires a finite axis default.",
                        target={"axisTag": tag},
                    ) from exc
                if not default.is_finite() or not minimum <= default <= maximum:
                    raise SourceBundleError(
                        "variable_location_unavailable",
                        "Variable feature compilation requires an in-range axis default.",
                        target={"axisTag": tag},
                    )
                axis = Axis()
                axis.axisTag = tag
                axis.minValue = float(minimum)
                axis.defaultValue = float(default)
                axis.maxValue = float(maximum)
                axis.flags = 0
                axis.axisNameID = 256 + index
                fvar.axes.append(axis)
            compile_font["fvar"] = fvar
        addOpenTypeFeaturesFromString(
            compile_font,
            parser_source,
            filename=str(path),
        )
    except SourceBundleError:
        raise
    except ImportError as exc:
        raise SourceBundleError(
            "dependency_unavailable",
            "Source-bundle validation requires FontTools feaLib.",
            target={"reference": "fontTools.feaLib", "path": str(path)},
        ) from exc
    except Exception as exc:
        raise SourceBundleError(
            "feature_compile_failed",
            "Generated OpenType feature source did not compile: {}".format(exc),
            target={"path": str(path)},
        ) from exc


def _manifest_contract_error(message: str, **target: Any) -> SourceBundleError:
    return SourceBundleError("manifest_contract_invalid", message, target=target)


def _require_closed_keys(
    value: Any,
    *,
    required: set[str],
    optional: set[str] | None = None,
    path: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _manifest_contract_error(
            "Manifest metadata must use JSON objects.", path=path
        )
    keys = {str(key) for key in value}
    allowed = required | set(optional or ())
    if not required <= keys or not keys <= allowed:
        raise _manifest_contract_error(
            "Manifest metadata has missing or unknown fields.",
            path=path,
            required=sorted(required),
            observed=sorted(keys),
        )
    return value


def _validate_manifest_contract(
    manifest: Any,
    *,
    root: Path,
    model: Mapping[str, Any],
    expected_targets: Sequence[str],
    inventory: Mapping[str, Mapping[str, Sequence[Path]]],
) -> list[dict[str, Any]]:
    manifest = _require_closed_keys(
        manifest,
        required={
            "schemaVersion",
            "bundleLayoutVersion",
            "canonicalModelSchemaVersion",
            "documentFingerprint",
            "compatibilityMode",
            "versions",
            "targets",
            "files",
            "fileCount",
            "treeSha256",
            "manifest",
        },
        optional={"sourceFingerprint"},
        path="$",
    )
    if manifest.get("schemaVersion") != 1:
        raise _manifest_contract_error(
            "Unsupported source-manifest schemaVersion.", path="$.schemaVersion"
        )
    if manifest.get("bundleLayoutVersion") != BUNDLE_LAYOUT_VERSION:
        raise _manifest_contract_error(
            "source-manifest bundleLayoutVersion does not match this runtime.",
            path="$.bundleLayoutVersion",
        )
    if manifest.get("canonicalModelSchemaVersion") != CANONICAL_MODEL_SCHEMA_VERSION:
        raise _manifest_contract_error(
            "source-manifest canonical model version does not match this runtime.",
            path="$.canonicalModelSchemaVersion",
        )
    if manifest.get("documentFingerprint") != fingerprint_model(model):
        raise _manifest_contract_error(
            "source-manifest document fingerprint does not match the canonical model.",
            path="$.documentFingerprint",
        )
    if manifest.get("compatibilityMode") not in {
        "component_preserving",
        "decomposed_export",
    }:
        raise _manifest_contract_error(
            "source-manifest compatibilityMode is invalid.",
            path="$.compatibilityMode",
        )
    source_fingerprint = manifest.get("sourceFingerprint")
    if source_fingerprint is not None and not re.fullmatch(
        r"sha256:[0-9a-f]{64}", str(source_fingerprint)
    ):
        raise _manifest_contract_error(
            "sourceFingerprint must be a lowercase SHA-256 fingerprint.",
            path="$.sourceFingerprint",
        )

    versions = _require_closed_keys(
        manifest.get("versions"),
        required={
            "application",
            "applicationVersion",
            "applicationBuild",
            "glyphsMcpServerVersion",
            "mcpApiVersion",
        },
        path="$.versions",
    )
    if any(not isinstance(value, str) or not value for value in versions.values()):
        raise _manifest_contract_error(
            "Every source-manifest version value must be a non-empty string.",
            path="$.versions",
        )
    if versions.get("glyphsMcpServerVersion") != str(SERVER_VERSION) or versions.get(
        "mcpApiVersion"
    ) != str(API_VERSION):
        raise _manifest_contract_error(
            "source-manifest MCP versions do not match this runtime.",
            path="$.versions",
        )

    self_record = _require_closed_keys(
        manifest.get("manifest"),
        required={"path", "selfHashExcluded"},
        path="$.manifest",
    )
    if self_record != {"path": MANIFEST_NAME, "selfHashExcluded": True}:
        raise _manifest_contract_error(
            "source-manifest must explicitly exclude only its own hash.",
            path="$.manifest",
        )

    targets = manifest.get("targets")
    if not isinstance(targets, list) or len(targets) != len(expected_targets):
        raise _manifest_contract_error(
            "source-manifest targets do not match the emitted target roots.",
            path="$.targets",
        )
    observed_kinds: list[str] = []
    for index, raw_target in enumerate(targets):
        target = _require_closed_keys(
            raw_target,
            required={
                "kind",
                "designspaceFiles",
                "masterUFOs",
                "braceUFOs",
                "featureMetadata",
                "fontmake",
            },
            path="$.targets[{}]".format(index),
        )
        kind = str(target.get("kind") or "")
        observed_kinds.append(kind)
        expected_designspaces = [
            path.relative_to(root).as_posix()
            for path in inventory.get(kind, {}).get("designspaces", ())
        ]
        expected_ufos = {
            path.relative_to(root).as_posix()
            for path in inventory.get(kind, {}).get("ufos", ())
        }
        designspace_files = target.get("designspaceFiles")
        master_ufos = target.get("masterUFOs")
        brace_ufos = target.get("braceUFOs")
        if designspace_files != expected_designspaces:
            raise _manifest_contract_error(
                "Manifest Designspace paths do not match the target tree.",
                path="$.targets[{}].designspaceFiles".format(index),
            )
        if not isinstance(master_ufos, list) or not isinstance(brace_ufos, list):
            raise _manifest_contract_error(
                "Manifest UFO paths must be arrays.",
                path="$.targets[{}]".format(index),
            )
        if len(set(master_ufos)) != len(master_ufos) or set(master_ufos) & set(
            brace_ufos
        ):
            raise _manifest_contract_error(
                "Manifest UFO paths must be unique and disjoint.",
                path="$.targets[{}]".format(index),
            )
        if set(master_ufos) | set(brace_ufos) != expected_ufos:
            raise _manifest_contract_error(
                "Manifest UFO paths do not match the target tree.",
                path="$.targets[{}]".format(index),
            )
        fontmake = _require_closed_keys(
            target.get("fontmake"),
            required=(
                {"masterArguments", "instanceArguments"}
                if kind == "static"
                else {"variableArguments"}
            ),
            path="$.targets[{}].fontmake".format(index),
        )
        if any(
            not isinstance(arguments, list)
            or not arguments
            or any(not isinstance(argument, str) or not argument for argument in arguments)
            for arguments in fontmake.values()
        ):
            raise _manifest_contract_error(
                "Manifest fontmake arguments must be non-empty string arrays.",
                path="$.targets[{}].fontmake".format(index),
            )
        expected_fontmake = (
            {
                "masterArguments": ["-M"],
                "instanceArguments": [
                    "-i",
                    "--interpolate-binary-layout",
                    "{compiledMasterDirectory}",
                ],
            }
            if kind == "static"
            else {"variableArguments": ["-o", "variable"]}
        )
        if dict(fontmake) != expected_fontmake:
            raise _manifest_contract_error(
                "Manifest fontmake workflow does not match the target contract.",
                path="$.targets[{}].fontmake".format(index),
            )
        if not isinstance(target.get("featureMetadata"), Mapping):
            raise _manifest_contract_error(
                "Manifest featureMetadata must be an object.",
                path="$.targets[{}].featureMetadata".format(index),
            )
    if observed_kinds != list(expected_targets):
        raise _manifest_contract_error(
            "Manifest target order does not match the validated layout.",
            path="$.targets",
        )

    files = manifest.get("files")
    if not isinstance(files, list):
        raise _manifest_contract_error(
            "Manifest files must be an array.", path="$.files"
        )
    for index, raw_record in enumerate(files):
        record = _require_closed_keys(
            raw_record,
            required={"path", "size", "sha256"},
            path="$.files[{}]".format(index),
        )
        if (
            not isinstance(record.get("path"), str)
            or record.get("path") == MANIFEST_NAME
            or not isinstance(record.get("size"), int)
            or isinstance(record.get("size"), bool)
            or record.get("size") < 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256") or ""))
        ):
            raise _manifest_contract_error(
                "Manifest file records must use path, byte size, and lowercase SHA-256.",
                path="$.files[{}]".format(index),
            )
    if (
        not isinstance(manifest.get("fileCount"), int)
        or isinstance(manifest.get("fileCount"), bool)
        or manifest.get("fileCount") != len(files)
    ):
        raise _manifest_contract_error(
            "Manifest fileCount does not match files.", path="$.fileCount"
        )
    records = _file_records(root)
    tree_digest = _records_digest(records)
    if files != records or manifest.get("treeSha256") != tree_digest:
        raise SourceBundleError(
            "manifest_verification_failed",
            "source-manifest.json does not match the staged bundle.",
        )
    return records


def validate_source_bundle(root: Path, *, model: Mapping[str, Any]) -> dict[str, Any]:
    if not root.is_dir():
        raise SourceBundleError("bundle_missing", "Source bundle directory is missing.")
    variable_enabled, _variable_reason = _variable_target_eligibility(model)
    expected_targets = ["static"] + (["variable"] if variable_enabled else [])
    masters = _items(model.get("masters", ()))
    inventory = _validate_exact_layout(
        root, expected_targets=expected_targets, master_count=len(masters)
    )
    location_definition_pattern = re.compile(r"(?m)^\s*locationDef\b")
    for target_kind in expected_targets:
        external_sources = inventory[target_kind]["features"]
        for path in external_sources:
            text = path.read_text(encoding="utf-8")
            has_named_locations = location_definition_pattern.search(text) is not None
            if target_kind == "variable":
                declaration_count = len(location_definition_pattern.findall(text))
                if not has_named_locations or declaration_count != len(masters):
                    raise SourceBundleError(
                        "feature_location_representation_invalid",
                        "The shared variable feature source must declare one deterministic named location per master.",
                        target={
                            "path": str(path.relative_to(root)),
                            "expected": len(masters),
                            "observed": declaration_count,
                        },
                    )
            elif has_named_locations:
                raise SourceBundleError(
                    "feature_location_representation_invalid",
                    "Static shared feature sources must not contain variable location declarations.",
                    target={"path": str(path.relative_to(root))},
                )
        for ufo in inventory[target_kind]["ufos"]:
            ufo_feature_path = ufo / "features.fea"
            if not ufo_feature_path.is_file():
                raise SourceBundleError(
                    "bundle_layout_invalid",
                    "Every source UFO must contain features.fea.",
                    target={"path": str(ufo_feature_path.relative_to(root))},
                )
            if location_definition_pattern.search(
                ufo_feature_path.read_text(encoding="utf-8")
            ):
                raise SourceBundleError(
                    "feature_location_representation_invalid",
                    "UFO-local feature sources must use pinned-feaLib-compatible inline locations.",
                    target={"path": str(ufo_feature_path.relative_to(root))},
                )
    glyph_names, _aliases, _glyphs = _glyph_inventory(model)
    feature_files = sorted(root.rglob("*.fea"))
    for path in feature_files:
        relative_parts = path.relative_to(root).parts
        _validate_feature_file(
            path,
            glyph_names,
            model=model,
            variable=bool(relative_parts and relative_parts[0] == "variable"),
        )
    for ufo in sorted(root.rglob("*.ufo")):
        if not ufo.is_dir():
            continue
        for name in ("metainfo.plist", "groups.plist", "kerning.plist", "lib.plist"):
            path = ufo / name
            if path.exists():
                _load_plist(path, {})
    _AxisDescriptor, DesignSpaceDocument, _RuleDescriptor, _SourceDescriptor = (
        _require_designspace_lib()
    )
    try:
        for target in expected_targets:
            for path in inventory[target]["designspaces"]:
                DesignSpaceDocument.fromfile(path)
    except Exception as exc:
        if isinstance(exc, SourceBundleError):
            raise
        raise SourceBundleError(
            "designspace_validation_failed",
            "Generated Designspace source did not parse: {}".format(exc),
        ) from exc
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise SourceBundleError(
            "manifest_missing", "The staged bundle omitted source-manifest.json."
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceBundleError(
            "manifest_contract_invalid",
            "source-manifest.json is not valid UTF-8 JSON.",
            target={"path": MANIFEST_NAME},
        ) from exc
    records = _validate_manifest_contract(
        manifest,
        root=root,
        model=model,
        expected_targets=expected_targets,
        inventory=inventory,
    )
    manifest_artifact = _manifest_artifact(root)
    bundle_fingerprint = _bundle_fingerprint(root)
    if len(
        {
            str(manifest["treeSha256"]),
            str(manifest_artifact["manifestSha256"]),
            str(bundle_fingerprint),
        }
    ) != 3:
        raise SourceBundleError(
            "manifest_contract_invalid",
            "Tree, manifest, and bundle hashes must be independently derived.",
        )
    return {
        "bundleLayoutVersion": BUNDLE_LAYOUT_VERSION,
        "bundleFingerprint": bundle_fingerprint,
        "manifestTreeSha256": manifest["treeSha256"],
        "manifestFileCount": manifest["fileCount"],
        "featureFileCount": len(feature_files),
        "ufoCount": sum(len(inventory[target]["ufos"]) for target in expected_targets),
        "manifest": manifest,
        **manifest_artifact,
    }


def native_source_renderer(
    font: Any,
    *,
    target_kind: str,
    destination: Path,
    compatibility_mode: str,
    decompose_glyphs: Sequence[str],
) -> Mapping[str, Any]:
    """Invoke the unchanged legacy outline renderer behind the v2 boundary."""

    try:
        from export_designspace_ufo import (  # type: ignore[import-not-found]
            ExportDesignspaceAndUFO,
            ExportOptions,
        )
    except Exception as exc:
        raise SourceBundleError(
            "native_renderer_unavailable",
            "The Glyphs UFO/Designspace outline renderer is unavailable.",
        ) from exc
    decomposed = compatibility_mode == "decomposed_export"
    options = ExportOptions(
        include_variable=target_kind == "variable",
        include_static=target_kind == "static",
        include_build_script=False,
        decompose_glyphs=tuple(decompose_glyphs) if decomposed else (),
        decompose_smart_components=decomposed,
        decompose_smart_corners=decomposed,
        output_directory=str(destination),
        open_destination=False,
    )
    result = ExportDesignspaceAndUFO(font, options=options).run()
    return {
        "designspaceFiles": list(result.designspace_files),
        "masterUFOs": list(result.master_ufos),
        "braceUFOs": list(result.brace_ufos),
        "supportFiles": list(result.support_files),
    }


def _result_paths(
    values: Sequence[Any], *, target_root: Path, bundle_root: Path
) -> list[str]:
    result = []
    for value in values:
        path = Path(str(value))
        if not path.is_absolute():
            path = target_root / path
        try:
            path.relative_to(target_root)
            result.append(path.relative_to(bundle_root).as_posix())
        except ValueError as exc:
            raise SourceBundleError(
                "native_renderer_path_escape",
                "The native renderer reported a path outside its target root.",
                target={"path": str(path)},
            ) from exc
    return result


def _require_designspace_lib() -> tuple[Any, Any, Any, Any]:
    try:
        from fontTools.designspaceLib import (
            AxisDescriptor,
            DesignSpaceDocument,
            RuleDescriptor,
            SourceDescriptor,
        )
    except ImportError as exc:
        raise SourceBundleError(
            "dependency_unavailable",
            "Source-bundle validation requires FontTools designspaceLib.",
            target={"reference": "fontTools.designspaceLib"},
        ) from exc
    return AxisDescriptor, DesignSpaceDocument, RuleDescriptor, SourceDescriptor


def _synthesize_single_master_designspace(
    *,
    target_root: Path,
    model: Mapping[str, Any],
    master_ufo: Path,
) -> Path:
    AxisDescriptor, DesignSpaceDocument, _RuleDescriptor, SourceDescriptor = (
        _require_designspace_lib()
    )
    document = DesignSpaceDocument()
    master = _items(model.get("masters", ()))[0]
    coordinates = {
        str(value.get("tag") or ""): value.get("internal")
        for value in _items(master.get("axes", ()), key_name="tag")
    }
    source_location: dict[str, float] = {}
    for axis_value in _items(model.get("axes", ())):
        tag = str(axis_value.get("tag") or "")
        if not re.fullmatch(r"[A-Za-z0-9]{4}", tag) or tag not in coordinates:
            continue
        try:
            coordinate = float(coordinates[tag])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(coordinate):
            continue
        axis = AxisDescriptor()
        axis.tag = tag
        axis.name = str(axis_value.get("name") or tag)
        axis.minimum = coordinate
        axis.default = coordinate
        axis.maximum = coordinate
        document.addAxis(axis)
        source_location[axis.name] = coordinate

    family_name = str(
        (model.get("font") or {}).get("familyName")
        if isinstance(model.get("font"), Mapping)
        else ""
    ) or "Source"
    source = SourceDescriptor()
    source.name = str(master.get("id") or "master")
    source.familyName = family_name
    source.styleName = str(master.get("name") or "Regular")
    source.path = str(master_ufo)
    source.location = source_location
    source.copyInfo = True
    document.addSource(source)
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "", family_name) or "Source"
    path = target_root / "{}.designspace".format(filename)
    document.write(path)
    return path


def _validate_reported_target_paths(
    *,
    target_kind: str,
    designspaces: Sequence[str],
    master_ufos: Sequence[str],
    brace_ufos: Sequence[str],
) -> None:
    expected_prefix = (target_kind, "masters")
    for relative in [*master_ufos, *brace_ufos]:
        parts = Path(relative).parts
        if (
            len(parts) != 3
            or tuple(parts[:2]) != expected_prefix
            or not parts[-1].endswith(".ufo")
        ):
            raise SourceBundleError(
                "bundle_layout_invalid",
                "Layout v2 requires every UFO at <target>/masters/*.ufo.",
                target={"targetKind": target_kind, "path": relative},
            )
    for relative in designspaces:
        parts = Path(relative).parts
        if len(parts) != 2 or parts[0] != target_kind or not parts[-1].endswith(
            ".designspace"
        ):
            raise SourceBundleError(
                "bundle_layout_invalid",
                "Layout v2 requires each Designspace at the target root.",
                target={"targetKind": target_kind, "path": relative},
            )


def _validate_exact_layout(
    root: Path, *, expected_targets: Sequence[str], master_count: int
) -> dict[str, dict[str, list[Path]]]:
    observed_roots = sorted(path.name for path in root.iterdir() if path.is_dir())
    if observed_roots != sorted(expected_targets):
        raise SourceBundleError(
            "bundle_layout_invalid",
            "Layout v2 target roots must match the model exactly.",
            target={
                "expected": sorted(expected_targets),
                "observed": observed_roots,
            },
        )
    unexpected_root_files = sorted(
        path.name
        for path in root.iterdir()
        if path.is_file() and path.name != MANIFEST_NAME
    )
    if unexpected_root_files:
        raise SourceBundleError(
            "bundle_layout_invalid",
            "Layout v2 permits only source-manifest.json at the bundle root.",
            target={"unexpected": unexpected_root_files},
        )

    inventory: dict[str, dict[str, list[Path]]] = {}
    _AxisDescriptor, DesignSpaceDocument, _RuleDescriptor, _SourceDescriptor = (
        _require_designspace_lib()
    )
    for target_kind in expected_targets:
        target_root = root / target_kind
        masters_root = target_root / "masters"
        features_root = target_root / "features"
        if not masters_root.is_dir():
            raise SourceBundleError(
                "bundle_layout_invalid",
                "Layout v2 omitted the required masters/ directory.",
                target={"targetKind": target_kind},
            )
        if not features_root.is_dir():
            raise SourceBundleError(
                "bundle_layout_invalid",
                "Layout v2 omitted the required features/ directory.",
                target={"targetKind": target_kind},
            )
        designspaces = sorted(target_root.rglob("*.designspace"))
        direct_designspaces = sorted(target_root.glob("*.designspace"))
        if len(direct_designspaces) != 1 or designspaces != direct_designspaces:
            raise SourceBundleError(
                "bundle_layout_invalid",
                "Layout v2 requires exactly one Designspace at each target root.",
                target={
                    "targetKind": target_kind,
                    "observed": [
                        path.relative_to(root).as_posix() for path in designspaces
                    ],
                },
            )
        allowed_target_entries = {
            masters_root,
            features_root,
            direct_designspaces[0],
        }
        observed_target_entries = set(target_root.iterdir())
        if observed_target_entries != allowed_target_entries:
            raise SourceBundleError(
                "bundle_layout_invalid",
                "Layout v2 target roots permit only one Designspace, masters/, and features/.",
                target={
                    "targetKind": target_kind,
                    "unexpected": sorted(
                        path.name
                        for path in observed_target_entries - allowed_target_entries
                    ),
                },
            )
        feature_entries = sorted(features_root.iterdir())
        external_feature_files = sorted(
            path
            for path in target_root.rglob("*.fea")
            if not any(
                part.endswith(".ufo")
                for part in path.relative_to(target_root).parts[:-1]
            )
        )
        expected_feature_count = master_count if target_kind == "static" else 1
        if (
            len(feature_entries) != expected_feature_count
            or any(not path.is_file() or path.suffix != ".fea" for path in feature_entries)
            or external_feature_files != feature_entries
        ):
            raise SourceBundleError(
                "bundle_layout_invalid",
                "Layout v2 requires all feature sources directly under <target>/features/.",
                target={
                    "targetKind": target_kind,
                    "expected": expected_feature_count,
                    "observed": [
                        path.relative_to(root).as_posix()
                        for path in external_feature_files
                    ],
                },
            )
        all_ufo_paths = sorted(target_root.rglob("*.ufo"))
        master_ufos = sorted(masters_root.glob("*.ufo"))
        if (
            any(not path.is_dir() for path in all_ufo_paths)
            or all_ufo_paths != master_ufos
            or len(master_ufos) < master_count
        ):
            raise SourceBundleError(
                "bundle_layout_invalid",
                "Layout v2 requires all UFOs directly under <target>/masters/.",
                target={
                    "targetKind": target_kind,
                    "expected": master_count,
                    "observed": [
                        path.relative_to(root).as_posix() for path in all_ufo_paths
                    ],
                },
            )
        try:
            designspace = DesignSpaceDocument.fromfile(direct_designspaces[0])
        except Exception as exc:
            raise SourceBundleError(
                "designspace_validation_failed",
                "Generated Designspace source did not parse.",
                target={"path": str(direct_designspaces[0])},
            ) from exc
        for source in designspace.sources:
            if not source.path:
                raise SourceBundleError(
                    "bundle_layout_invalid",
                    "Every Designspace source must reference a masters/*.ufo path.",
                    target={"targetKind": target_kind, "name": str(source.name or "")},
                )
            source_path = Path(source.path).resolve(strict=False)
            try:
                relative = source_path.relative_to(masters_root.resolve())
            except ValueError as exc:
                raise SourceBundleError(
                    "bundle_layout_invalid",
                    "A Designspace source escaped the target masters/ directory.",
                    target={"targetKind": target_kind, "path": str(source.path)},
                ) from exc
            if len(relative.parts) != 1 or not source_path.is_dir():
                raise SourceBundleError(
                    "bundle_layout_invalid",
                    "A Designspace source does not reference a direct masters/*.ufo.",
                    target={"targetKind": target_kind, "path": str(source.path)},
                )
        inventory[target_kind] = {
            "designspaces": direct_designspaces,
            "ufos": master_ufos,
            "features": feature_entries,
        }
    return inventory


def _component_graph(model: Mapping[str, Any]) -> dict[str, set[str]]:
    _order, _aliases, glyphs = _glyph_inventory(model)
    graph: dict[str, set[str]] = {name: set() for name in glyphs}
    for glyph_name, glyph in glyphs.items():
        layers = glyph.get("layers", ())
        layer_values = layers.values() if isinstance(layers, Mapping) else layers
        if not isinstance(layer_values, Iterable) or isinstance(
            layer_values, (str, bytes, bytearray)
        ):
            continue
        for layer in layer_values:
            if not isinstance(layer, Mapping):
                continue
            for component in _items(layer.get("components", ())):
                name = str(
                    component.get("name") or component.get("componentName") or ""
                )
                if name:
                    graph[glyph_name].add(name)
            for shape in _items(layer.get("shapes", ())):
                if str(shape.get("kind") or "") != "component":
                    continue
                value = shape.get("value")
                if isinstance(value, Mapping):
                    name = str(
                        value.get("name") or value.get("componentName") or ""
                    )
                    if name:
                        graph[glyph_name].add(name)
    return graph


def _validate_decomposition_graph(
    model: Mapping[str, Any], roots: Sequence[str]
) -> None:
    graph = _component_graph(model)
    visiting: list[str] = []
    complete: set[str] = set()

    def visit(name: str) -> None:
        if name not in graph:
            raise SourceBundleError(
                "component_reference_missing",
                "Decomposed export references a missing component glyph.",
                target={"componentName": name, "dependencyPath": visiting + [name]},
            )
        if name in visiting:
            start = visiting.index(name)
            raise SourceBundleError(
                "component_cycle",
                "Decomposed export cannot resolve a cyclic component graph.",
                target={"glyphNames": visiting[start:] + [name]},
            )
        if name in complete:
            return
        visiting.append(name)
        for dependency in sorted(graph[name]):
            visit(dependency)
        visiting.pop()
        complete.add(name)

    for root in roots:
        visit(root)


def _layer_component_signature(layer: Mapping[str, Any]) -> tuple[str, ...]:
    result: list[str] = []
    for component in _items(layer.get("components", ())):
        name = str(component.get("name") or component.get("componentName") or "")
        if name:
            result.append(name)
    for shape in _items(layer.get("shapes", ())):
        if str(shape.get("kind") or "") != "component":
            continue
        value = shape.get("value")
        if isinstance(value, Mapping):
            name = str(value.get("name") or value.get("componentName") or "")
            if name:
                result.append(name)
    return tuple(result)


def _validate_component_topology(
    model: Mapping[str, Any], roots: Sequence[str]
) -> None:
    _validate_decomposition_graph(model, roots)
    _order, _aliases, glyphs = _glyph_inventory(model)
    for glyph_name in roots:
        glyph = glyphs[glyph_name]
        layers = _items(glyph.get("layers", ()))
        master_signatures: dict[str, tuple[str, ...]] = {}
        special_layers: list[Mapping[str, Any]] = []
        for layer in layers:
            if bool(layer.get("isMasterLayer")) or "master" in _sequence_strings(
                layer.get("roles", ())
            ):
                master_signatures[str(layer.get("masterId") or layer.get("id") or "")] = (
                    _layer_component_signature(layer)
                )
            elif bool(layer.get("isSpecialLayer")):
                special_layers.append(layer)
        if len(set(master_signatures.values())) > 1:
            raise SourceBundleError(
                "component_topology_incompatible",
                "Component-preserving export requires matching component topology across masters.",
                target={
                    "glyphName": glyph_name,
                    "sequence": [
                        "{}:{}".format(key, ",".join(value))
                        for key, value in sorted(master_signatures.items())
                    ],
                },
            )
        for layer in special_layers:
            roles = set(_sequence_strings(layer.get("roles", ())))
            if "intermediate" not in roles:
                continue
            master_id = str(layer.get("masterId") or "")
            expected = master_signatures.get(master_id)
            observed = _layer_component_signature(layer)
            if expected is not None and observed != expected:
                raise SourceBundleError(
                    "component_topology_incompatible",
                    "An intermediate layer has incompatible component topology.",
                    target={
                        "glyphName": glyph_name,
                        "layerId": str(layer.get("id") or ""),
                        "masterId": master_id,
                        "expected": list(expected),
                        "observed": list(observed),
                    },
                )


@dataclass(frozen=True)
class _IntermediateLayer:
    glyph_name: str
    layer_id: str
    master_id: str
    location: tuple[tuple[str, Decimal], ...]


@dataclass(frozen=True)
class _LayerExportPlan:
    exporting_glyphs: tuple[str, ...]
    intermediate_layers: tuple[_IntermediateLayer, ...]


def _special_layer_coordinate(
    value: Any,
    *,
    glyph_name: str,
    layer_id: str,
    axis_tag: str,
) -> Decimal:
    if isinstance(value, bool):
        raise SourceBundleError(
            "special_layer_unrepresentable",
            "Intermediate-layer coordinates must be finite numbers.",
            target={
                "glyphName": glyph_name,
                "layerId": layer_id,
                "axisTag": axis_tag,
            },
        )
    try:
        coordinate = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SourceBundleError(
            "special_layer_unrepresentable",
            "Intermediate-layer coordinates must be finite numbers.",
            target={
                "glyphName": glyph_name,
                "layerId": layer_id,
                "axisTag": axis_tag,
            },
        ) from exc
    if not coordinate.is_finite():
        raise SourceBundleError(
            "special_layer_unrepresentable",
            "Intermediate-layer coordinates must be finite numbers.",
            target={
                "glyphName": glyph_name,
                "layerId": layer_id,
                "axisTag": axis_tag,
            },
        )
    return coordinate


def _plan_exporting_layers(
    model: Mapping[str, Any], *, master_ids: Sequence[str]
) -> _LayerExportPlan:
    """Bind every exporting master/special layer to a representable target.

    The native v2 renderer can preserve ordinary master layers and coordinate-
    bearing intermediate layers. Other Glyphs special-layer domains need a
    richer target representation and therefore block before native export
    instead of silently disappearing.
    """

    glyph_order, _aliases, glyphs = _glyph_inventory(model)
    exporting_glyphs = tuple(
        name for name in glyph_order if glyphs[name].get("export") is not False
    )
    declared_masters = set(master_ids)
    axis_tags = tuple(
        str(axis.get("tag") or "") for axis in _items(model.get("axes", ()))
    )
    intermediates: list[_IntermediateLayer] = []

    for glyph_name in exporting_glyphs:
        layers = _items(glyphs[glyph_name].get("layers", ()))
        master_layers: dict[str, list[str]] = {}
        seen_layer_ids: set[str] = set()
        seen_intermediate_locations: set[tuple[tuple[str, Decimal], ...]] = set()
        for layer in layers:
            layer_id = str(layer.get("id") or "")
            if layer_id and layer_id in seen_layer_ids:
                raise SourceBundleError(
                    "export_layer_identity_collision",
                    "An exporting glyph has duplicate layer identities.",
                    target={"glyphName": glyph_name, "layerId": layer_id},
                )
            if layer_id:
                seen_layer_ids.add(layer_id)
            roles = set(_sequence_strings(layer.get("roles", ())))
            is_master = bool(layer.get("isMasterLayer")) or "master" in roles
            is_special = bool(layer.get("isSpecialLayer")) or bool(
                roles.intersection({"intermediate", "alternate", "smart", "color"})
            )
            if is_master:
                master_id = str(layer.get("masterId") or layer_id)
                if master_id not in declared_masters:
                    raise SourceBundleError(
                        "export_layer_master_unresolved",
                        "A master layer references an unknown canonical master.",
                        target={
                            "glyphName": glyph_name,
                            "layerId": layer_id,
                            "masterId": master_id,
                        },
                    )
                master_layers.setdefault(master_id, []).append(layer_id)
                continue
            if not is_special:
                continue

            interpolation = layer.get("interpolation")
            kind = (
                str(interpolation.get("kind") or "")
                if isinstance(interpolation, Mapping)
                else ""
            )
            unsupported_roles = roles.intersection({"alternate", "smart", "color"})
            if kind != "intermediate" or unsupported_roles:
                raise SourceBundleError(
                    "special_layer_unsupported",
                    "This exporting special-layer domain cannot be represented losslessly by layout v2.",
                    target={
                        "glyphName": glyph_name,
                        "layerId": layer_id,
                        "kind": kind or (sorted(unsupported_roles)[0] if unsupported_roles else "unknown"),
                    },
                )
            if not layer_id:
                raise SourceBundleError(
                    "special_layer_unrepresentable",
                    "Every exporting intermediate layer requires a stable identity.",
                    target={"glyphName": glyph_name, "kind": "intermediate"},
                )
            master_id = str(layer.get("masterId") or "")
            if master_id not in declared_masters:
                raise SourceBundleError(
                    "export_layer_master_unresolved",
                    "An intermediate layer references an unknown associated master.",
                    target={
                        "glyphName": glyph_name,
                        "layerId": layer_id,
                        "masterId": master_id,
                    },
                )
            coordinates = interpolation.get("coordinates")
            if not isinstance(coordinates, Mapping):
                raise SourceBundleError(
                    "special_layer_unrepresentable",
                    "Intermediate layers require a complete axis-coordinate mapping.",
                    target={"glyphName": glyph_name, "layerId": layer_id},
                )
            coordinate_tags = {str(tag) for tag in coordinates}
            if coordinate_tags != set(axis_tags) or not axis_tags:
                raise SourceBundleError(
                    "special_layer_unrepresentable",
                    "Intermediate layers require exactly one coordinate for every design axis.",
                    target={
                        "glyphName": glyph_name,
                        "layerId": layer_id,
                        "missing": sorted(set(axis_tags) - coordinate_tags),
                        "extra": sorted(coordinate_tags - set(axis_tags)),
                    },
                )
            location = tuple(
                (
                    tag,
                    _special_layer_coordinate(
                        coordinates[tag],
                        glyph_name=glyph_name,
                        layer_id=layer_id,
                        axis_tag=tag,
                    ),
                )
                for tag in axis_tags
            )
            if location in seen_intermediate_locations:
                raise SourceBundleError(
                    "special_layer_location_collision",
                    "An exporting glyph has multiple intermediate layers at one location.",
                    target={
                        "glyphName": glyph_name,
                        "layerId": layer_id,
                        "location": ",".join(
                            "{}={}".format(tag, _fea_decimal(value, target={}))
                            for tag, value in location
                        ),
                    },
                )
            seen_intermediate_locations.add(location)
            intermediates.append(
                _IntermediateLayer(
                    glyph_name=glyph_name,
                    layer_id=layer_id,
                    master_id=master_id,
                    location=location,
                )
            )

        missing_masters = sorted(declared_masters - set(master_layers))
        if missing_masters:
            raise SourceBundleError(
                "export_master_layer_missing",
                "Every exporting glyph requires one layer for every canonical master.",
                target={"glyphName": glyph_name, "missing": missing_masters},
            )
        for master_id, layer_ids in sorted(master_layers.items()):
            if len(layer_ids) != 1:
                raise SourceBundleError(
                    "export_master_layer_duplicate",
                    "An exporting glyph has multiple layers for one canonical master.",
                    target={
                        "glyphName": glyph_name,
                        "masterId": master_id,
                        "layerIds": layer_ids,
                    },
                )

    return _LayerExportPlan(
        exporting_glyphs=exporting_glyphs,
        intermediate_layers=tuple(intermediates),
    )


def _ufo_layer_glyphs(ufo_path: Path, layer_name: str | None) -> set[str]:
    if layer_name is None:
        directory = "glyphs"
    else:
        layer_contents = _load_plist(ufo_path / "layercontents.plist", [])
        if not isinstance(layer_contents, list):
            raise SourceBundleError(
                "ufo_layer_inventory_invalid",
                "UFO layercontents.plist must contain a layer inventory.",
                target={"path": str(ufo_path / "layercontents.plist")},
            )
        directory = ""
        for entry in layer_contents:
            if (
                isinstance(entry, (list, tuple))
                and len(entry) == 2
                and str(entry[0]) == layer_name
            ):
                directory = str(entry[1])
                break
        if not directory:
            return set()
    contents_path = ufo_path / directory / "contents.plist"
    contents = _load_plist(contents_path, {})
    if not isinstance(contents, Mapping):
        raise SourceBundleError(
            "ufo_layer_inventory_invalid",
            "A UFO glyph layer must contain a contents.plist dictionary.",
            target={"path": str(contents_path)},
        )
    return {str(name) for name in contents}


def _designspace_source_location(document: Any, source: Any) -> tuple[tuple[str, Decimal], ...]:
    try:
        raw_location = source.getFullDesignLocation(document)
    except Exception:
        raw_location = source.designLocation or source.location or {}
    result = []
    for axis in document.axes:
        name = str(axis.name or axis.tag or "")
        value = raw_location.get(name, axis.default)
        try:
            coordinate = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise SourceBundleError(
                "designspace_source_location_invalid",
                "A generated Designspace source has an invalid design location.",
                target={"name": str(source.name or ""), "axisTag": str(axis.tag or "")},
            ) from exc
        if not coordinate.is_finite():
            raise SourceBundleError(
                "designspace_source_location_invalid",
                "A generated Designspace source has an invalid design location.",
                target={"name": str(source.name or ""), "axisTag": str(axis.tag or "")},
            )
        result.append((name, coordinate))
    return tuple(result)


def _verify_exported_layers(
    *,
    designspace_path: Path,
    model: Mapping[str, Any],
    emitted_ufos: Sequence[Path],
    plan: _LayerExportPlan,
    target_kind: str,
) -> None:
    try:
        from fontTools.designspaceLib import DesignSpaceDocument

        document = DesignSpaceDocument.fromfile(designspace_path)
    except Exception as exc:
        raise SourceBundleError(
            "designspace_validation_failed",
            "Generated Designspace source did not parse during layer verification.",
            target={"path": str(designspace_path)},
        ) from exc

    emitted = {path.resolve(strict=False): path for path in emitted_ufos}
    source_records = []
    for source in document.sources:
        if not source.path:
            raise SourceBundleError(
                "export_layer_omitted",
                "A generated Designspace source has no emitted UFO backing it.",
                target={"targetKind": target_kind, "name": str(source.name or "")},
            )
        source_path = Path(source.path).resolve(strict=False)
        if source_path not in emitted:
            raise SourceBundleError(
                "export_layer_omitted",
                "A generated Designspace source references an unreported UFO.",
                target={"targetKind": target_kind, "path": str(source.path)},
            )
        source_records.append(
            (
                source,
                source_path,
                str(source.layerName or "") or None,
                _designspace_source_location(document, source),
            )
        )

    default_sources = [record for record in source_records if record[2] is None]
    default_paths = [record[1] for record in default_sources]
    if len(default_sources) != len(_items(model.get("masters", ()))) or set(
        default_paths
    ) != set(emitted):
        raise SourceBundleError(
            "export_master_layer_omitted",
            "Generated Designspace default sources do not account for every master UFO.",
            target={
                "targetKind": target_kind,
                "expected": len(_items(model.get("masters", ()))),
                "observed": len(default_sources),
            },
        )
    expected_master_locations = []
    for master in _items(model.get("masters", ())):
        master_id = str(master.get("id") or "")
        coordinates = {
            str(item.get("tag") or ""): item.get("internal")
            for item in _items(master.get("axes", ()), key_name="tag")
        }
        location = []
        for axis in document.axes:
            tag = str(axis.tag or "")
            if tag not in coordinates:
                raise SourceBundleError(
                    "export_master_location_invalid",
                    "A canonical master has no coordinate for an emitted Designspace axis.",
                    target={"masterId": master_id, "axisTag": tag},
                )
            try:
                value = Decimal(str(coordinates[tag]))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise SourceBundleError(
                    "export_master_location_invalid",
                    "A canonical master has an invalid Designspace coordinate.",
                    target={"masterId": master_id, "axisTag": tag},
                ) from exc
            if not value.is_finite():
                raise SourceBundleError(
                    "export_master_location_invalid",
                    "A canonical master has an invalid Designspace coordinate.",
                    target={"masterId": master_id, "axisTag": tag},
                )
            location.append((str(axis.name or tag), value))
        expected_master_locations.append(tuple(location))
    observed_master_locations = [record[3] for record in default_sources]
    if sorted(expected_master_locations) != sorted(observed_master_locations):
        raise SourceBundleError(
            "export_master_layer_omitted",
            "Generated Designspace source locations do not match the canonical masters.",
            target={
                "targetKind": target_kind,
                "expected": [
                    ",".join("{}={}".format(name, value) for name, value in location)
                    for location in sorted(expected_master_locations)
                ],
                "observed": [
                    ",".join("{}={}".format(name, value) for name, value in location)
                    for location in sorted(observed_master_locations)
                ],
            },
        )
    for _source, source_path, _layer_name, _location in default_sources:
        missing_glyphs = sorted(
            set(plan.exporting_glyphs) - _ufo_layer_glyphs(source_path, None)
        )
        if missing_glyphs:
            raise SourceBundleError(
                "export_master_layer_omitted",
                "A generated master UFO omitted exporting glyph layers.",
                target={
                    "targetKind": target_kind,
                    "path": str(source_path),
                    "glyphNames": missing_glyphs,
                },
            )

    axis_names = {str(axis.tag or ""): str(axis.name or axis.tag or "") for axis in document.axes}
    planned_by_location: dict[
        tuple[tuple[str, Decimal], ...], list[_IntermediateLayer]
    ] = {}
    for layer in plan.intermediate_layers:
        location = tuple((axis_names[tag], value) for tag, value in layer.location)
        planned_by_location.setdefault(location, []).append(layer)

    special_sources = [record for record in source_records if record[2] is not None]
    observed_locations = {record[3] for record in special_sources}
    unexpected = sorted(
        ",".join("{}={}".format(name, value) for name, value in record[3])
        for record in special_sources
        if record[3] not in planned_by_location
    )
    if unexpected:
        raise SourceBundleError(
            "export_special_layer_unexpected",
            "Generated Designspace contains special sources absent from the canonical model.",
            target={"targetKind": target_kind, "unexpected": unexpected},
        )
    missing_locations = [
        location for location in planned_by_location if location not in observed_locations
    ]
    if missing_locations:
        raise SourceBundleError(
            "export_special_layer_omitted",
            "Native export omitted one or more canonical intermediate-layer locations.",
            target={
                "targetKind": target_kind,
                "missing": [
                    ",".join("{}={}".format(name, value) for name, value in location)
                    for location in missing_locations
                ],
            },
        )
    for location, layers in planned_by_location.items():
        candidates = [record for record in special_sources if record[3] == location]
        if len(candidates) != 1:
            raise SourceBundleError(
                "export_special_layer_ambiguous",
                "Each intermediate location must map to exactly one Designspace source.",
                target={
                    "targetKind": target_kind,
                    "location": ",".join(
                        "{}={}".format(name, value) for name, value in location
                    ),
                    "observed": len(candidates),
                },
            )
        _source, source_path, layer_name, _observed = candidates[0]
        glyphs = _ufo_layer_glyphs(source_path, layer_name)
        missing_glyphs = sorted(
            layer.glyph_name for layer in layers if layer.glyph_name not in glyphs
        )
        if missing_glyphs:
            raise SourceBundleError(
                "export_special_layer_omitted",
                "A generated UFO layer omitted canonical intermediate glyph layers.",
                target={
                    "targetKind": target_kind,
                    "path": str(source_path),
                    "glyphNames": missing_glyphs,
                },
            )


_VOLATILE_NATIVE_KEYS = {
    "exportedat",
    "exportsession",
    "generatedat",
    "lastchange",
    "lastmodified",
    "session",
    "sessionid",
    "sessionuuid",
    "timestamp",
}


def _is_volatile_native_key(key: Any) -> bool:
    leaf = str(key or "").rsplit(".", 1)[-1].replace("_", "").lower()
    return leaf in _VOLATILE_NATIVE_KEYS


def _strip_volatile_native_values(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_volatile_native_values(item)
            for key, item in value.items()
            if not _is_volatile_native_key(key)
        }
    if isinstance(value, list):
        return [_strip_volatile_native_values(item) for item in value]
    return value


def _normalize_native_metadata(target_root: Path) -> None:
    for path in sorted(target_root.rglob("*.plist")):
        value = _load_plist(path, {})
        normalized = _strip_volatile_native_values(value)
        if normalized != value:
            _write_plist(path, normalized)
    for path in sorted(target_root.rglob("*.designspace")):
        try:
            from fontTools.designspaceLib import DesignSpaceDocument

            document = DesignSpaceDocument.fromfile(path)
            normalized = _strip_volatile_native_values(document.lib)
            if normalized != document.lib:
                document.lib = normalized
                document.write(path)
        except Exception as exc:
            raise SourceBundleError(
                "designspace_validation_failed",
                "Generated Designspace metadata could not be normalized.",
                target={"path": str(path)},
            ) from exc
    for path in sorted(target_root.rglob("*.glif")):
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            raise SourceBundleError(
                "glif_validation_failed",
                "Native export produced malformed GLIF XML.",
                target={"path": str(path)},
            ) from exc
        changed = False
        for dictionary in tree.iter("dict"):
            children = list(dictionary)
            index = 0
            while index + 1 < len(children):
                key = children[index]
                if key.tag == "key" and _is_volatile_native_key(key.text):
                    dictionary.remove(key)
                    dictionary.remove(children[index + 1])
                    changed = True
                    index += 2
                    continue
                index += 1
        if changed:
            tree.write(path, encoding="utf-8", xml_declaration=True)


def _verify_decomposed_ufos(root: Path) -> None:
    for path in sorted(root.rglob("*.glif")):
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            raise SourceBundleError(
                "glif_validation_failed",
                "Native export produced malformed GLIF XML.",
                target={"path": str(path)},
            ) from exc
        component = next(
            (
                node
                for node in tree.getroot().iter()
                if str(node.tag).rsplit("}", 1)[-1] == "component"
            ),
            None,
        )
        if component is not None:
            raise SourceBundleError(
                "decomposition_incomplete",
                "decomposed_export left a component in the emitted UFO sources.",
                target={
                    "path": str(path.relative_to(root)),
                    "base": component.attrib.get("base"),
                },
            )


def render_source_bundle(
    *,
    font: Any,
    model: Mapping[str, Any],
    destination: Path,
    compatibility_mode: str,
    document_fingerprint: str | None = None,
    source_fingerprint: str | None = None,
    runtime_versions: Mapping[str, Any] | None = None,
    native_renderer: Any = None,
) -> dict[str, Any]:
    """Regenerate, normalise, manifest, and validate one layout-v2 bundle."""

    if compatibility_mode not in {"component_preserving", "decomposed_export"}:
        raise SourceBundleError(
            "compatibility_mode_invalid",
            "compatibilityMode must be component_preserving or decomposed_export.",
        )
    expected_fingerprint = str(document_fingerprint or fingerprint_model(model))
    actual_fingerprint = fingerprint_model(model)
    if expected_fingerprint != actual_fingerprint:
        raise SourceBundleError(
            "document_fingerprint_mismatch",
            "The canonical document does not match the export plan fingerprint.",
        )
    destination = Path(destination)
    if destination.exists():
        raise SourceBundleError(
            "staging_not_empty",
            "The v2 renderer requires a new staging directory.",
            target={"path": str(destination)},
        )
    destination.mkdir(parents=True)
    renderer = native_renderer or native_source_renderer
    glyph_order, _aliases, glyphs = _glyph_inventory(model)
    decompose_glyphs = [
        name for name in glyph_order if glyphs[name].get("export") is not False
    ]
    if compatibility_mode == "component_preserving":
        _validate_component_topology(model, decompose_glyphs)
    else:
        _validate_decomposition_graph(model, decompose_glyphs)
    masters = _items(model.get("masters", ()))
    master_ids = [str(master.get("id") or "") for master in masters]
    if not master_ids or any(not master_id for master_id in master_ids):
        raise SourceBundleError(
            "master_required",
            "Source-bundle export requires at least one identified master.",
        )
    if len(set(master_ids)) != len(master_ids):
        raise SourceBundleError(
            "master_identity_collision", "Source-bundle masters must have unique IDs."
        )
    layer_plan = _plan_exporting_layers(model, master_ids=master_ids)
    variable_enabled, variable_omission_reason = _variable_target_eligibility(model)
    target_kinds = ["static"] + (["variable"] if variable_enabled else [])
    target_results: list[dict[str, Any]] = []
    all_designspaces: list[str] = []
    all_master_ufos: list[str] = []
    all_brace_ufos: list[str] = []
    all_support: list[str] = []

    for target_kind in target_kinds:
        target_root = destination / target_kind
        native_result = dict(
            renderer(
                font,
                target_kind=target_kind,
                destination=target_root,
                compatibility_mode=compatibility_mode,
                decompose_glyphs=decompose_glyphs,
            )
        )
        rendered_ufos = []
        for value in native_result.get("masterUFOs", ()):
            path = Path(str(value))
            rendered_ufos.append(path if path.is_absolute() else target_root / path)
        if len(rendered_ufos) != len(master_ids):
            raise SourceBundleError(
                "native_master_count_mismatch",
                "Native UFO count does not match the canonical master count.",
                target={
                    "targetKind": target_kind,
                    "expected": len(master_ids),
                    "observed": len(rendered_ufos),
                },
            )

        legacy_features = target_root / "features"
        if legacy_features.exists():
            shutil.rmtree(legacy_features)
        legacy_features.mkdir(parents=True)
        feature_metadata_by_master: dict[str, Mapping[str, Any]] = {}
        condition_rules: list[Mapping[str, Any]] = []
        if target_kind == "variable":
            source, metadata = build_feature_source(
                model,
                target_kind="variable",
                location_syntax="named",
            )
            condition_rules = list(metadata.get("conditionRules") or [])
            shared_path = legacy_features / "features.fea"
            shared_path.write_text(source, encoding="utf-8", newline="\n")
            all_support.append(shared_path.relative_to(destination).as_posix())
            for master_id, ufo_path in zip(master_ids, rendered_ufos):
                ufo_source, ufo_metadata = build_feature_source(
                    model,
                    target_kind="variable",
                    master_id=master_id,
                    location_syntax="inline",
                )
                rewrite_ufo_source(
                    ufo_path,
                    model=model,
                    master_id=master_id,
                    feature_source=ufo_source,
                    feature_metadata=ufo_metadata,
                )
                feature_metadata_by_master[master_id] = ufo_metadata
        else:
            for master_id, ufo_path in zip(master_ids, rendered_ufos):
                source, metadata = build_feature_source(
                    model, target_kind="static", master_id=master_id
                )
                shared_path = legacy_features / "{}.fea".format(
                    _safe_identifier(master_id, prefix="master")
                )
                shared_path.write_text(source, encoding="utf-8", newline="\n")
                all_support.append(shared_path.relative_to(destination).as_posix())
                rewrite_ufo_source(
                    ufo_path,
                    model=model,
                    master_id=master_id,
                    feature_source=source,
                    feature_metadata=metadata,
                )
                feature_metadata_by_master[master_id] = metadata

        designspaces = _result_paths(
            native_result.get("designspaceFiles", ()),
            target_root=target_root,
            bundle_root=destination,
        )
        master_ufos = _result_paths(
            native_result.get("masterUFOs", ()),
            target_root=target_root,
            bundle_root=destination,
        )
        brace_ufos = _result_paths(
            native_result.get("braceUFOs", ()),
            target_root=target_root,
            bundle_root=destination,
        )
        native_support = _result_paths(
            native_result.get("supportFiles", ()),
            target_root=target_root,
            bundle_root=destination,
        )
        if not designspaces and target_kind == "static" and len(master_ids) == 1:
            synthesized = _synthesize_single_master_designspace(
                target_root=target_root,
                model=model,
                master_ufo=destination / master_ufos[0],
            )
            designspaces = [synthesized.relative_to(destination).as_posix()]
        if len(designspaces) != 1:
            raise SourceBundleError(
                "bundle_layout_invalid",
                "Layout v2 requires exactly one Designspace for every emitted target.",
                target={
                    "targetKind": target_kind,
                    "observed": list(designspaces),
                },
            )
        _validate_reported_target_paths(
            target_kind=target_kind,
            designspaces=designspaces,
            master_ufos=master_ufos,
            brace_ufos=brace_ufos,
        )
        _verify_exported_layers(
            designspace_path=destination / designspaces[0],
            model=model,
            emitted_ufos=[
                destination / relative for relative in [*master_ufos, *brace_ufos]
            ],
            plan=layer_plan,
            target_kind=target_kind,
        )
        native_support = [
            relative
            for relative in native_support
            if (destination / relative).is_file()
        ]
        for relative in designspaces:
            _write_designspace_condition_rules(
                destination / relative,
                condition_rules if target_kind == "variable" else (),
            )
        _normalize_native_metadata(target_root)
        if compatibility_mode == "decomposed_export":
            _verify_decomposed_ufos(target_root)
        all_designspaces.extend(designspaces)
        all_master_ufos.extend(master_ufos)
        all_brace_ufos.extend(brace_ufos)
        all_support.extend(native_support)
        target_results.append(
            {
                "kind": target_kind,
                "designspaceFiles": designspaces,
                "masterUFOs": master_ufos,
                "braceUFOs": brace_ufos,
                "featureMetadata": {
                    key: dict(value)
                    for key, value in sorted(feature_metadata_by_master.items())
                },
                "fontmake": (
                    {
                        "masterArguments": ["-M"],
                        "instanceArguments": [
                            "-i",
                            "--interpolate-binary-layout",
                            "{compiledMasterDirectory}",
                        ],
                    }
                    if target_kind == "static"
                    else {"variableArguments": ["-o", "variable"]}
                ),
            }
        )

    manifest = write_source_manifest(
        destination,
        document_fingerprint=expected_fingerprint,
        source_fingerprint=source_fingerprint,
        compatibility_mode=compatibility_mode,
        runtime_versions=dict(runtime_versions or {}),
        targets=target_results,
    )
    validation = validate_source_bundle(destination, model=model)
    return {
        "bundleLayoutVersion": BUNDLE_LAYOUT_VERSION,
        "targetKinds": target_kinds,
        "variableTargetOmittedReason": variable_omission_reason,
        "designspaceFiles": sorted(set(all_designspaces)),
        "masterUFOs": sorted(set(all_master_ufos)),
        "braceUFOs": sorted(set(all_brace_ufos)),
        "supportFiles": sorted(set(all_support + [MANIFEST_NAME])),
        "buildHelperIncluded": False,
        "compatibilityMode": compatibility_mode,
        "manifestTreeSha256": manifest["treeSha256"],
        "manifestFileCount": manifest["fileCount"],
        "manifestSize": validation["manifestSize"],
        "manifestSha256": validation["manifestSha256"],
        "bundleFingerprint": validation["bundleFingerprint"],
        "preflight": {
            key: value
            for key, value in validation.items()
            if key != "manifest"
        },
    }


def preflight_source_bundle(
    *,
    font: Any,
    model: Mapping[str, Any],
    compatibility_mode: str,
    document_fingerprint: str,
    source_fingerprint: str | None = None,
    runtime_versions: Mapping[str, Any] | None = None,
    native_renderer: Any = None,
) -> dict[str, Any]:
    """Regenerate and validate in an ephemeral directory; persist no staging."""

    with tempfile.TemporaryDirectory(prefix="glyphs-mcp-v2-review-") as temporary:
        return render_source_bundle(
            font=font,
            model=model,
            destination=Path(temporary) / "bundle",
            compatibility_mode=compatibility_mode,
            document_fingerprint=document_fingerprint,
            source_fingerprint=source_fingerprint,
            runtime_versions=runtime_versions,
            native_renderer=native_renderer,
        )


__all__ = [
    "BUNDLE_LAYOUT_VERSION",
    "ExportPlan",
    "MANIFEST_NAME",
    "SOURCE_KERNING_LIB_KEY",
    "SourceBundleError",
    "build_feature_source",
    "normalize_feature_code",
    "native_source_renderer",
    "preflight_source_bundle",
    "render_source_bundle",
    "resolve_number_values",
    "rewrite_ufo_source",
    "select_variable_blocks",
    "validate_source_bundle",
    "write_source_manifest",
]
