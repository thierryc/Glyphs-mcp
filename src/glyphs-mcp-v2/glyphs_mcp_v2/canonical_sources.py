"""Source-neutral entry points for canonical font-state comparison.

Parsing bytes is deliberately outside this module. Callers provide either a
live ``GSFont`` or an already-decoded flat/package mapping; both normalize to
the same schema-v7 semantic tree before hashing or diffing.
"""

from __future__ import annotations

import copy
import math
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .canonical_schema import CANONICAL_SCHEMA, FieldRole, deterministic_occurrence_id
from .canonical_collections import canonical_glyph_id, canonical_kerning_domain


class CanonicalSource(Protocol):
    def capture(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class LiveGlyphsSource:
    font: Any
    capture_function: Callable[[Any], Mapping[str, Any]]

    def __init__(
        self,
        font: Any,
        *,
        capture: Callable[[Any], Mapping[str, Any]],
    ) -> None:
        object.__setattr__(self, "font", font)
        object.__setattr__(self, "capture_function", capture)

    def capture(self) -> Mapping[str, Any]:
        value = self.capture_function(self.font)
        materialize = getattr(value, "materialize", None)
        if callable(materialize):
            value = materialize()
        return copy.deepcopy(dict(value))


def _mapping(value: Any) -> dict[str, Any]:
    # ``SerializedMappingSource.capture`` takes one ownership copy at the
    # source boundary. Nested conversion must use shallow views: recursively
    # deep-copying a glyph again for every layer, shape, and node turns a
    # linear font capture into multiplicative work on real fonts.
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"", "0", "0.0", "false", "no"}:
            return False
        if text in {"1", "1.0", "true", "yes"}:
            return True
    return bool(value)


def _text(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _layer_metrics_key(value: Any) -> str | None:
    """Return the semantic spelling of a layer-local metrics key.

    Glyphs' file records already carry layer ownership, so they persist one
    leading equals sign where the live API exposes the explicit local-key
    spelling with two.  Canonical state keeps the explicit spelling and makes
    the conversion idempotent for native flattened mappings.
    """

    text = _text(value)
    if text is None or text.startswith("=="):
        return text
    return "={}".format(text) if text.startswith("=") else "=={}".format(text)


def canonical_image_path(value: Any, document_path: Any = None) -> str | None:
    """Normalize an image path relative to its font document when possible."""

    text = _text(value)
    if text is None:
        return None
    normalized = os.path.normpath(text)
    if document_path not in (None, "") and not os.path.isabs(normalized):
        # Glyphs 4 can expose an assigned absolute GSBackgroundImage path
        # without its leading slash. Recognize that spelling only when it
        # contains the complete owning document directory; shorter ordinary
        # relative paths remain relative and are never guessed.
        root = os.path.dirname(os.path.abspath(str(document_path)))
        stripped_root = root.lstrip(os.sep)
        if normalized == stripped_root or normalized.startswith(
            stripped_root + os.sep
        ):
            normalized = os.sep + normalized
    if not os.path.isabs(normalized) or document_path in (None, ""):
        return normalized.replace(os.sep, "/")
    root = os.path.dirname(os.path.abspath(str(document_path)))
    try:
        if os.path.commonpath((root, normalized)) == root:
            return os.path.relpath(normalized, root).replace(os.sep, "/")
    except ValueError:
        pass
    return normalized


def _number(value: Any, default: Any = None) -> int | float | Any:
    """Normalize one schema-known numeric OpenStep atom.

    Foundation decodes bare numeric atoms in Glyphs' OpenStep files as
    strings, while the live serializer exposes NSNumber values. Coercion is
    deliberately limited to fields whose semantic type is known; arbitrary
    user data may legitimately contain a numeric-looking string.
    """

    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value
    text = str(value).strip()
    try:
        return int(text, 10)
    except ValueError:
        try:
            number = float(text)
        except ValueError:
            return value
        if not math.isfinite(number):
            raise ValueError("serialized Glyphs number must be finite")
        return int(number) if number.is_integer() else number


def _numeric_tree(value: Any) -> Any:
    """Normalize leaves in a schema-known numeric container."""

    if isinstance(value, Mapping):
        return {str(key): _numeric_tree(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_numeric_tree(item) for item in value]
    return _number(value)


_EXTENSION_NUMBER_PATTERN = re.compile(
    r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$"
)


_EXTENSION_TEXT_KEY_SUFFIXES = (
    "code",
    "id",
    "label",
    "name",
    "note",
    "path",
    "tag",
    "text",
    "url",
)


def _extension_key_is_textual(key: str | None) -> bool:
    normalized = str(key or "").replace("_", "").lower()
    return bool(normalized) and normalized.endswith(_EXTENSION_TEXT_KEY_SUFFIXES)


def canonical_extension_value(value: Any, *, _key: str | None = None) -> Any:
    """Normalize format-v4 extension atoms without erasing opaque strings.

    Glyphs' saved-file decoder exposes bare OpenStep numeric atoms as numbers,
    while the live ``GSFlattenDictionary`` boundary can expose those same
    atoms as strings after a document becomes dirty. Extension containers are
    otherwise schema-open, so coercion is deliberately limited to canonical
    number spellings. Values such as ``"001"`` remain strings.
    """

    if isinstance(value, Mapping):
        return {
            str(key): canonical_extension_value(item, _key=str(key))
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [canonical_extension_value(item) for item in value]
    if (
        _extension_key_is_textual(_key)
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        return str(int(value)) if float(value).is_integer() else str(value)
    if (
        isinstance(value, str)
        and not _extension_key_is_textual(_key)
        and _EXTENSION_NUMBER_PATTERN.fullmatch(value.strip())
    ):
        return _number(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return copy.deepcopy(value)


def _extension_mapping(value: Any) -> dict[str, Any]:
    return dict(canonical_extension_value(_mapping(value)))


def _point(value: Any, default: tuple[float, float] = (0.0, 0.0)) -> list[Any]:
    values = _sequence(value)
    if len(values) >= 2:
        return [_number(values[0]), _number(values[1])]
    return [_number(default[0]), _number(default[1])]


def _occurrence_records(
    values: Any,
    *,
    kind: str,
    semantic: Callable[[Mapping[str, Any]], str],
    convert: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    result = []
    for raw in _sequence(values):
        item = _mapping(raw)
        key = semantic(item)
        occurrence = counts.get(key, 0)
        counts[key] = occurrence + 1
        result.append(
            {
                "id": deterministic_occurrence_id(kind, key, occurrence),
                **dict(convert(item)),
            }
        )
    return result


def _parameters(values: Any) -> list[dict[str, Any]]:
    return _occurrence_records(
        values,
        kind="parameter",
        semantic=lambda item: str(item.get("name") or ""),
        convert=lambda item: {
            "name": str(item.get("name") or ""),
            "value": canonical_extension_value(item.get("value")),
            "disabled": _bool(item.get("disabled")),
        },
    )


def canonical_info_property(
    key: Any, value: Any, values: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Normalize one localized property across file and ObjectWrapper views.

    Glyphs' native ``GSProperty`` exposes the default localized value both as
    ``value`` and as a language entry whose language is the empty string. The
    v4 file format writes that same state once in ``values`` using ``dflt``.
    Collapse the native projection so both sources share one semantic record.
    """

    localized = [
        {
            "language": str(item.get("language") or "dflt"),
            "value": canonical_extension_value(item.get("value")),
        }
        for item in values
    ]
    scalar = canonical_extension_value(value)
    default_value = next(
        (
            item.get("value")
            for item in localized
            if item.get("language") == "dflt"
        ),
        object(),
    )
    if localized and scalar == default_value:
        scalar = None
    return {
        "key": str(key or ""),
        "value": scalar,
        "values": localized,
    }


def _properties(values: Any) -> list[dict[str, Any]]:
    return _occurrence_records(
        values,
        kind="property",
        semantic=lambda item: str(item.get("key") or ""),
        convert=lambda item: canonical_info_property(
            item.get("key"),
            item.get("value"),
            [
                {
                    "language": str(_mapping(value).get("language") or ""),
                    "value": _mapping(value).get("value"),
                }
                for value in _sequence(item.get("values"))
            ],
        ),
    )


def _default_property_text(
    properties: Sequence[Mapping[str, Any]], keys: Sequence[str]
) -> str:
    accepted = frozenset(str(key) for key in keys)
    for item in properties:
        if str(item.get("key") or "") not in accepted:
            continue
        if item.get("value") not in (None, ""):
            return str(item["value"])
        values = _sequence(item.get("values"))
        default = next(
            (
                _mapping(value).get("value")
                for value in values
                if str(_mapping(value).get("language") or "") == "dflt"
            ),
            None,
        )
        if default not in (None, ""):
            return str(default)
        if values:
            return str(_mapping(values[0]).get("value") or "")
    return ""


def _family_name(properties: Sequence[Mapping[str, Any]]) -> str:
    return _default_property_text(properties, ("familyName", "familyNames"))


def _axes(values: Any) -> list[dict[str, Any]]:
    result = []
    for raw in _sequence(values):
        item = _mapping(raw)
        tag = str(item.get("tag") or "")
        if not tag:
            raise ValueError("serialized Glyphs axis is missing its tag")
        result.append(
            {
                "id": tag,
                "tag": tag,
                "name": str(item.get("name") or ""),
                "names": copy.deepcopy(item.get("names") or []),
                "default": _number(item.get("default")),
                "hidden": _bool(item.get("hidden")),
                "userData": _extension_mapping(item.get("userData")),
            }
        )
    return result


def _metric_records(values: Any, kind: str) -> list[dict[str, Any]]:
    def normalized(item: Mapping[str, Any]) -> dict[str, Any]:
        raw_type = item.get("type")
        if raw_type in (0, "0", "0.0", ""):
            raw_type = None
        return {
            "type": CANONICAL_SCHEMA.canonical_value_for_official(
                "definition.metric", "type", raw_type
            ),
            "name": str(item.get("name") or ""),
            "horizontal": _bool(item.get("horizontal")),
            "filter": _text(item.get("filter")),
        }

    def semantic(item: Mapping[str, Any]) -> str:
        value = normalized(item)
        return "{}:{}:{}:{}".format(
            value["type"],
            value["name"],
            value["horizontal"],
            value["filter"] or "",
        )

    return _occurrence_records(
        values,
        kind=kind,
        semantic=semantic,
        convert=normalized,
    )


def _bound_metric_store(
    values: Any, definition_ids: Sequence[str]
) -> list[dict[str, Any]]:
    records = _sequence(values)
    return [
        {
            "id": (
                str(definition_ids[index])
                if index < len(definition_ids)
                else deterministic_occurrence_id("metricValue", "unbound", index)
            ),
            "pos": _number(_mapping(value).get("pos"), 0),
            "over": _number(_mapping(value).get("over"), 0),
        }
        for index, value in enumerate(records)
    ]


def _bound_scalar_store(
    values: Any, definition_ids: Sequence[str], *, kind: str
) -> list[dict[str, Any]]:
    records = _sequence(values)
    return [
        {
            "id": (
                str(definition_ids[index])
                if index < len(definition_ids)
                else deterministic_occurrence_id(
                    "{}Value".format(kind), "unbound", index
                )
            ),
            "value": _number(
                (
                    _mapping(value).get("value")
                    if "value" in _mapping(value)
                    else _mapping(value).get("width")
                    if "width" in _mapping(value)
                    else value
                ),
                0,
            ),
        }
        for index, value in enumerate(records)
    ]


def _generic_records(
    values: Any, kind: str, fields: Sequence[str]
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    result = []
    for raw in _sequence(values):
        item = _mapping(raw)
        semantic = str(item.get("name") or item.get("type") or kind)
        occurrence = counts.get(semantic, 0)
        counts[semantic] = occurrence + 1
        canonical = {}
        for name in fields:
            value = item.get(name, _RECORD_DEFAULTS.get(kind, {}).get(name))
            canonical[name] = canonical_record_value(kind, name, value)
        result.append(
            {
                "id": deterministic_occurrence_id(kind, semantic, occurrence),
                **canonical,
            }
        )
    return result


_WRITABLE = (FieldRole.WRITABLE,)
_ANNOTATION_FIELDS = CANONICAL_SCHEMA.fields_for(
    "definition.annotation", roles=_WRITABLE
)
_GUIDE_FIELDS = CANONICAL_SCHEMA.fields_for(
    "definition.guide", roles=_WRITABLE
)
_HINT_FIELDS = CANONICAL_SCHEMA.fields_for(
    "definition.hint", roles=_WRITABLE
)
_RECORD_DEFAULTS: Mapping[str, Mapping[str, Any]] = {
    "anchor": {"orientation": "left"},
    "annotation": {"angle": 0, "pos": [0, 0], "text": "", "width": 0},
    "guide": {
        "angle": 0,
        "attr": {},
        "grid": 0,
        "length": 0,
        "lockAngle": False,
        "locked": False,
        "name": "",
        "orientation": "left",
        "pos": [0, 0],
        "showMeasurement": False,
        "size": [0, 0],
        "slope": False,
        "type": "Line",
    },
    "hint": {"horizontal": False, "options": 0, "scale": [1, 1]},
}


def canonical_record_value(kind: str, name: str, value: Any) -> Any:
    """Normalize one registered record leaf across saved and live sources."""

    if value is None and name in _RECORD_DEFAULTS.get(kind, {}):
        value = _RECORD_DEFAULTS[kind][name]
    # Glyphs exposes an absent hint stem as Foundation's NSNotFound. The v4
    # document schema owns a signed 32-bit stem index, so the 64-bit sentinel
    # is not document content and must converge with an omitted saved field.
    if kind == "hint" and name == "stem":
        try:
            if abs(int(value)) > 2**31 - 1:
                value = None
        except (TypeError, ValueError):
            pass
    try:
        if name in {"orientation", "type"}:
            value = _number(value)
        value = CANONICAL_SCHEMA.canonical_value_for_official(
            "definition.{}".format(kind), name, value
        )
    except KeyError:
        pass
    if name in {"pos", "scale", "size"} and value is not None:
        return _point(value)
    if name == "attr":
        return _extension_mapping(value)
    if name in {"lockAngle", "locked", "showMeasurement", "slope", "horizontal"}:
        return _bool(value)
    if name in {
        "angle", "bottomValue", "grid", "length", "options",
        "origin", "other1", "other2", "place", "stem", "target",
        "topValue", "width",
    }:
        return _number(value)
    return copy.deepcopy(value)


_LAYER_SCALAR_DEFAULTS: Mapping[str, Any] = {
    "active": True,
    "vertOrigin": 0,
    "vertWidth": 0,
    "visible": False,
}


def canonical_layer_scalar(name: str, value: Any) -> Any:
    """Normalize one official layer scalar across serialized and live sources."""

    if value is None and name in _LAYER_SCALAR_DEFAULTS:
        value = _LAYER_SCALAR_DEFAULTS[name]
    if name in {"active", "visible"}:
        return _bool(value, bool(_LAYER_SCALAR_DEFAULTS[name]))
    if name in {"width", "vertOrigin", "vertWidth"}:
        return _number(value)
    if name == "color":
        return _numeric_tree(value)
    return copy.deepcopy(value)


def _anchors(values: Any) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    result = []
    for raw in _sequence(values):
        item = _mapping(raw)
        name = str(item.get("name") or "")
        occurrence = counts.get(name, 0)
        counts[name] = occurrence + 1
        attributes = _extension_mapping(item.get("attr"))
        user_data = _extension_mapping(attributes.pop("userData", {}))
        result.append(
            {
                "id": deterministic_occurrence_id("anchor", name, occurrence),
                "name": name,
                "position": _point(item.get("pos")),
                "orientation": canonical_record_value(
                    "anchor", "orientation", item.get("orientation")
                ),
                "locked": _bool(item.get("locked")),
                "attributes": attributes,
                "userData": user_data,
            }
        )
    return result


_NODE_TYPES = {
    "m": "move",
    "l": "line",
    "c": "curve",
    "q": "qcurve",
    "u": "quartic",
    "h": "hobby",
    "r": "spiral",
    "o": "offcurve",
}

_EXPANDED_NODE_TYPES = {
    "1": "line",
    "35": "curve",
    "36": "qcurve",
    "37": "hobby",
    "38": "quartic",
    "39": "spiral",
    "65": "offcurve",
    "line": "line",
    "curve": "curve",
    "cubiccurve": "curve",
    "offcurve": "offcurve",
    "qcurve": "qcurve",
    "quadraticcurve": "qcurve",
    "quart": "quartic",
    "quarticcurve": "quartic",
    "hobbycurve": "hobby",
    "raphnewspiral": "spiral",
    "move": "move",
}


def _expanded_node(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize GlyphsCore's documented GSNode dictionary representation.

    Saved format-v4 documents use compact node arrays. The public native
    ``GSNode.propertyListValueFormat:error:`` boundary uses the equivalent
    expanded dictionary while GlyphsCore is constructing an in-memory
    property tree. Accepting both here keeps live and serialized sources on
    the same canonical conversion path.
    """

    item = _mapping(raw)
    position = _point(item.get("pos", item.get("position")))
    raw_type = str(item.get("type") or "line")
    type_key = raw_type.replace("GSNodeType", "").replace("_", "").lower()
    node_type = _EXPANDED_NODE_TYPES.get(type_key, type_key)
    # GlyphsCore's flattened format-v4 mapping abbreviates this field as
    # ``conn`` while the public expanded schema names it ``connection``.
    # They are the same persisted node-connection value.
    connection = item.get(
        "connection", item.get("conn", item.get("smooth", False))
    )
    connection_key = str(connection).replace("GSNodeConnection", "").lower()
    smooth = _bool(item.get("smooth", False)) or connection_key in {
        "100",
        "102",
        "smooth",
        "supersmooth",
        "tangent",
    }
    raw_orientation = _number(item.get("orientation", 0))
    orientation = {
        "left": 0,
        "center": 1,
        "right": 2,
    }.get(str(raw_orientation).lower(), raw_orientation)
    attributes = _extension_mapping(item.get("attr", item.get("attributes")))
    if "userData" in item and "userData" not in attributes:
        attributes["userData"] = _extension_mapping(item.get("userData"))
    if "hoiInfo" in item and "hoi" not in attributes:
        attributes["hoi"] = _extension_mapping(item.get("hoiInfo"))
    return {
        "x": position[0],
        "y": position[1],
        "type": node_type,
        "smooth": smooth,
        "name": _text(item.get("name")),
        "orientation": orientation,
        "locked": _bool(item.get("locked")),
        "attributes": attributes,
    }


def _path(item: Mapping[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    nodes = []
    for raw in _sequence(item.get("nodes")):
        if isinstance(raw, Mapping):
            node = _expanded_node(raw)
            node_type = str(node["type"])
            occurrence = counts.get(node_type, 0)
            counts[node_type] = occurrence + 1
            nodes.append(
                {
                    "id": deterministic_occurrence_id(
                        "node", node_type, occurrence
                    ),
                    **node,
                }
            )
            continue
        values = _sequence(raw)
        if len(values) < 3:
            raise ValueError("serialized Glyphs node is incomplete")
        configuration = str(values[2])
        node_type = _NODE_TYPES.get(configuration[:1].lower(), configuration[:1].lower())
        occurrence = counts.get(node_type, 0)
        counts[node_type] = occurrence + 1
        nodes.append(
            {
                "id": deterministic_occurrence_id("node", node_type, occurrence),
                "x": _number(values[0]),
                "y": _number(values[1]),
                "type": node_type,
                "smooth": "s" in configuration.lower() or "t" in configuration.lower(),
                "name": None,
                "orientation": 2 if "R" in configuration else 1 if "C" in configuration else 0,
                "locked": "X" in configuration,
                "attributes": _extension_mapping(
                    values[3] if len(values) > 3 else {}
                ),
            }
        )
    return {
        "closed": _bool(item.get("closed"), True),
        "locked": _bool(item.get("locked")),
        "attributes": _extension_mapping(item.get("attr")),
        "nodes": nodes,
    }


def canonical_component(item: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one component from official format-v4 saved fields.

    Live PyObjC getters and decoded files converge on the authoritative saved
    decomposition. Effective alignment and affine transforms are observations,
    not independently writable document state.
    """

    alignment = _number(item.get("alignment", 0))
    return {
        "name": str(item.get("ref") or ""),
        "position": _point(item.get("pos")),
        "scale": _point(item.get("scale"), (1.0, 1.0)),
        "angle": _number(item.get("angle", 0)),
        "slant": _point(item.get("slant")),
        "alignment": alignment,
        "anchor": _text(item.get("anchor")),
        "locked": _bool(item.get("locked")),
        "masterId": _text(item.get("masterId")),
        "orientation": CANONICAL_SCHEMA.canonical_value_for_official(
            "definition.component",
            "orientation",
            _number(item.get("orientation", 0)),
        ),
        "keepWeight": _number(item.get("keepWeight", 0)),
        "traverseAnchors": _bool(item.get("traverseAnchors"), True),
        "attributes": _extension_mapping(item.get("attr")),
        "piece": _extension_mapping(item.get("piece")),
    }


def _image(
    item: Mapping[str, Any], *, document_path: Any = None
) -> dict[str, Any]:
    return {
        "imagePath": canonical_image_path(
            item.get("imagePath"), document_path
        ),
        "imageURL": _text(item.get("imageURL")),
        "position": _point(item.get("pos")),
        "scale": _point(item.get("scale"), (1.0, 1.0)),
        "crop": _numeric_tree(item.get("crop")),
        "angle": _number(item.get("angle", 0)),
        "slant": _point(item.get("slant")),
        "alpha": _number(item.get("alpha", 50)),
        "locked": _bool(item.get("locked")),
        "attributes": _extension_mapping(item.get("attr")),
    }


def _shapes(values: Any, *, document_path: Any = None) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    result = []
    for raw in _sequence(values):
        item = _mapping(raw)
        if "nodes" in item:
            kind, value = "path", _path(item)
        elif "ref" in item:
            kind, value = "component", canonical_component(item)
        elif "imagePath" in item or "imageURL" in item:
            kind, value = "image", _image(item, document_path=document_path)
        elif "groupId" in item:
            kind, value = "shape_group", {
                "groupId": str(item.get("groupId") or ""),
                "attributes": _extension_mapping(item.get("attr")),
            }
        else:
            raise ValueError("serialized Glyphs shape does not match a registered kind")
        occurrence = counts.get(kind, 0)
        counts[kind] = occurrence + 1
        result.append(
            {
                "id": deterministic_occurrence_id("shape", kind, occurrence),
                "kind": kind,
                "value": value,
            }
        )
    return result


def _background(item: Any, *, document_path: Any = None) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    source = _mapping(item)
    result = {
        "anchors": _anchors(source.get("anchors")),
        "annotations": _generic_records(
            source.get("annotations"), "annotation", _ANNOTATION_FIELDS
        ),
        "backgroundImage": _image(
            _mapping(source["backgroundImage"]), document_path=document_path
        )
        if isinstance(source.get("backgroundImage"), Mapping)
        else None,
        "guides": _generic_records(source.get("guides"), "guide", _GUIDE_FIELDS),
        "hints": _generic_records(source.get("hints"), "hint", _HINT_FIELDS),
        "shapes": _shapes(source.get("shapes"), document_path=document_path),
    }
    # Glyphs may materialize a lazy empty GSLayer background while cloning an
    # otherwise background-free layer. The file format omits that object.
    # Both representations carry exactly the same semantic document state.
    return result if any(value not in (None, [], {}) for value in result.values()) else None


def _layer(
    raw: Mapping[str, Any], *, master_names: Mapping[str, str], document_path: Any = None
) -> dict[str, Any]:
    item = _mapping(raw)
    layer_id = str(item.get("layerId") or "")
    master_id = str(item.get("associatedMasterId") or layer_id)
    attributes = _extension_mapping(item.get("attr"))
    coordinates = attributes.pop("coordinates", None)
    rules = attributes.pop("axisRules", None)
    if isinstance(coordinates, Mapping):
        interpolation: dict[str, Any] | None = {
            "kind": "intermediate",
            "coordinates": _numeric_tree(coordinates),
        }
    elif isinstance(rules, Mapping):
        interpolation = {
            "kind": "alternate",
            "ranges": {
                str(tag): {
                    "min": _number(_mapping(rule).get("min")),
                    "max": _number(_mapping(rule).get("max")),
                }
                for tag, rule in rules.items()
            },
        }
    else:
        interpolation = None
    is_master = layer_id in master_names and layer_id == master_id
    roles = (
        ["master"]
        if is_master
        else ["intermediate"]
        if interpolation and interpolation["kind"] == "intermediate"
        else ["alternate"]
        if interpolation
        else ["color"]
        if any(key in attributes for key in ("colorPalette", "sbixSize", "svg"))
        else ["backup"]
    )
    metric_aliases = {
        "leftMetricsKey": "metricLeft",
        "rightMetricsKey": "metricRight",
        "widthMetricsKey": "metricWidth",
        "bottomMetricsKey": "metricBottom",
        "topMetricsKey": "metricTop",
        "vertOriginMetricsKey": "metricVertOrigin",
        "vertWidthMetricsKey": "metricVertWidth",
    }
    result = {
        "id": layer_id,
        "masterId": master_id,
        # Master-layer names are a projection of their owning master. The
        # format normally omits the redundant layer field while the live API
        # returns the master name. Canonicalize both sources to the semantic
        # value instead of treating that projection as an edit.
        "name": (
            str(master_names.get(layer_id) or "")
            if is_master
            else str(item.get("name") or "")
        ),
        "roles": roles,
        "isMasterLayer": is_master,
        "isSpecialLayer": bool(interpolation) or roles[0] == "color",
        "interpolation": interpolation,
        "attributes": attributes,
        "anchors": _anchors(item.get("anchors")),
        "annotations": _generic_records(
            item.get("annotations"), "annotation", _ANNOTATION_FIELDS
        ),
        "background": _background(
            item.get("background"), document_path=document_path
        ),
        "backgroundImage": _image(
            _mapping(item["backgroundImage"]), document_path=document_path
        )
        if isinstance(item.get("backgroundImage"), Mapping)
        else None,
        "guides": _generic_records(item.get("guides"), "guide", _GUIDE_FIELDS),
        "hints": _generic_records(item.get("hints"), "hint", _HINT_FIELDS),
        "partSelection": canonical_extension_value(item.get("partSelection")),
        "shapes": _shapes(item.get("shapes"), document_path=document_path),
        "userData": _extension_mapping(item.get("userData")),
        "width": canonical_layer_scalar("width", item.get("width")),
        "vertOrigin": canonical_layer_scalar("vertOrigin", item.get("vertOrigin")),
        "vertWidth": canonical_layer_scalar("vertWidth", item.get("vertWidth")),
        "active": canonical_layer_scalar("active", item.get("active")),
        "visible": canonical_layer_scalar("visible", item.get("visible")),
        "color": canonical_layer_scalar("color", item.get("color")),
    }
    result.update(
        {
            canonical: _layer_metrics_key(item.get(serialized))
            for canonical, serialized in metric_aliases.items()
        }
    )
    return result


def _masters(
    values: Any,
    axes: Sequence[Mapping[str, Any]],
    *,
    metric_ids: Sequence[str] = (),
    stem_ids: Sequence[str] = (),
    number_ids: Sequence[str] = (),
) -> list[dict[str, Any]]:
    result = []
    for raw in _sequence(values):
        item = _mapping(raw)
        positions = _sequence(item.get("axesValues"))
        result.append(
            {
                "id": str(item.get("id") or ""),
                # GlyphsCore may omit the default master name from an
                # in-memory format-v4 tree even when a saved v4 package spells
                # it explicitly. The host-facing semantic default is Regular.
                "name": str(item.get("name") or "Regular"),
                "italicAngle": _number(item.get("italicAngle"), 0),
                "active": _bool(item.get("active"), True),
                "visible": _bool(item.get("visible"), True),
                "iconName": str(item.get("iconName", "Regular")),
                "axes": [
                    {
                        "tag": axis.get("tag"),
                        "internal": _number(positions[index])
                        if index < len(positions)
                        else None,
                    }
                    for index, axis in enumerate(axes)
                ],
                "customParameters": _parameters(item.get("customParameters")),
                "properties": _properties(item.get("properties")),
                "guides": _generic_records(
                    item.get("guides"), "guide", _GUIDE_FIELDS
                ),
                "metricValues": _bound_metric_store(
                    item.get("metricValues"), metric_ids
                ),
                "stemValues": _bound_scalar_store(
                    item.get("stemValues"), stem_ids, kind="stem"
                ),
                "numberValues": _bound_scalar_store(
                    item.get("numberValues"), number_ids, kind="number"
                ),
                "userData": _extension_mapping(item.get("userData")),
            }
        )
    return result


def canonical_root_from_serialized_records(
    root: str,
    records: Any,
    *,
    context: Mapping[str, Any],
) -> Any:
    """Normalize one bounded official record collection.

    This is the record-level counterpart to ``SerializedMappingSource``. It
    reuses the same converters when the adapter can serialize affected native
    records independently, avoiding a complete font or glyph-tree capture.
    """

    values = _sequence(records)
    converters = {
        "axes": lambda: _axes(values),
        "masters": lambda: _masters(
            values,
            _sequence(context.get("axes")),
            metric_ids=[
                str(value.get("id") or "")
                for value in _sequence(context.get("metrics"))
                if isinstance(value, Mapping)
            ],
            stem_ids=[
                str(value.get("id") or "")
                for value in _sequence(context.get("stems"))
                if isinstance(value, Mapping)
            ],
            number_ids=[
                str(value.get("id") or "")
                for value in _sequence(context.get("numbers"))
                if isinstance(value, Mapping)
            ],
        ),
        "instances": lambda: _instances(
            values,
            _sequence(context.get("axes")),
            instance_ids=[
                str(value.get("id") or "")
                for value in _sequence(context.get("instances"))
                if isinstance(value, Mapping)
            ],
        ),
        "metrics": lambda: _metric_records(values, "metric"),
        "stems": lambda: _metric_records(values, "stem"),
        "numbers": lambda: _metric_records(values, "number"),
        "features": lambda: _code_collection(values, "features"),
        "classes": lambda: _code_collection(values, "classes"),
        "featurePrefixes": lambda: _code_collection(
            values, "featurePrefixes"
        ),
    }
    converter = converters.get(root)
    if converter is None:
        raise ValueError(
            "canonical root is not an official record collection: {}".format(root)
        )
    return converter()


def _instances(
    values: Any,
    axes: Sequence[Mapping[str, Any]],
    *,
    instance_ids: Sequence[str] = (),
) -> list[dict[str, Any]]:
    records = _sequence(values)
    identities = tuple(str(value) for value in instance_ids)
    if identities and len(identities) != len(records):
        raise ValueError(
            "serialized instance records do not match the canonical identity context"
        )
    result = []
    for index, raw in enumerate(records):
        item = _mapping(raw)
        positions = _sequence(item.get("axesValues"))
        variable = str(item.get("type")).lower() in {"variable", "1"}
        manual_interpolation = _bool(item.get("manualInterpolation"))
        properties = _properties(item.get("properties"))
        canonical_positions = [
            _number(positions[axis_index])
            if axis_index < len(positions)
            else 0
            if variable
            else None
            for axis_index in range(len(axes))
        ]
        result.append(
            {
                "id": identities[index]
                if identities
                else "instance_{}".format(index),
                # Format v4 owns the instance name through the localized
                # ``styleNames`` property. The ObjectWrapper exposes
                # ``GSInstance.name`` as a convenience projection only.
                "name": _default_property_text(properties, ("styleNames",)),
                "type": "variable" if variable else "static",
                "included": _bool(item.get("exports"), True),
                "inclusionReason": None,
                "interpolationSupported": not variable,
                "exports": _bool(item.get("exports"), True),
                "visible": _bool(item.get("visible"), True),
                "isBold": _bool(item.get("isBold")),
                "isItalic": _bool(item.get("isItalic")),
                "linkStyle": _text(item.get("linkStyle")),
                "manualInterpolation": manual_interpolation,
                "weightClass": _number(item.get("weightClass", 400)),
                "widthClass": _number(item.get("widthClass", 5)),
                "instanceInterpolations": (
                    _numeric_tree(item.get("instanceInterpolations", {}))
                    if manual_interpolation
                    else {}
                ),
                "customParameters": _parameters(item.get("customParameters")),
                "properties": properties,
                "userData": _extension_mapping(item.get("userData")),
                "axes": [
                    {
                        "tag": axis.get("tag"),
                        "internal": canonical_positions[axis_index],
                        # Format v4 specifies ``axesValues`` as the external
                        # coordinate too when no separately mapped value is
                        # present. Keep the effective semantic coordinate so
                        # saved/package and live ObjectWrapper sources agree.
                        "external": canonical_positions[axis_index],
                    }
                    for axis_index, axis in enumerate(axes)
                ],
            }
        )
    return result


def _canonical_unicode(value: Any) -> str | None:
    """Normalize serialized code points to Glyphs' uppercase hex spelling."""

    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and int(value) == value:
        codepoint = int(value)
    else:
        text = str(value).strip().upper()
        if text.startswith("U+"):
            radix = 16
            text = text[2:]
        elif text.isdecimal():
            # Glyphs File Format v4 stores Unicode values as decimal integers.
            # Foundation's OpenStep reader projects those bare integers as
            # strings, so ``65`` must remain U+0041 rather than become U+0065.
            radix = 10
        else:
            radix = 16
        try:
            codepoint = int(text, radix)
        except ValueError:
            return text
    if codepoint < 0 or codepoint > 0x10FFFF:
        raise ValueError("Unicode code point is outside the valid range")
    return "{:04X}".format(codepoint)


def canonical_glyph_from_serialized(
    raw: Mapping[str, Any],
    master_names: Mapping[str, str],
    *,
    document_path: Any = None,
) -> dict[str, Any]:
    """Convert one official v4 glyph record into its canonical shard."""

    item = _mapping(raw)
    name = str(item.get("glyphname") or "")
    unicodes = [
        normalized
        for value in _sequence(item.get("unicode"))
        for normalized in (_canonical_unicode(value),)
        if normalized is not None
    ]
    if not unicodes and item.get("unicode") not in (None, ""):
        normalized = _canonical_unicode(item["unicode"])
        unicodes = [normalized] if normalized is not None else []
    aliases = {
        "leftKerningGroup": "kernLeft",
        "rightKerningGroup": "kernRight",
        "topKerningGroup": "kernTop",
        "bottomKerningGroup": "kernBottom",
        "productionName": "production",
    }
    result = {
        "name": name,
        "id": canonical_glyph_id(name),
        "mastersCompatible": True,
        "layers": [
            _layer(
                _mapping(layer),
                master_names=master_names,
                document_path=document_path,
            )
            for layer in _sequence(item.get("layers"))
        ],
        "category": item.get("category"),
        "subCategory": item.get("subCategory"),
        "unicode": unicodes[0] if unicodes else None,
        "export": _bool(item.get("export"), True),
        "script": item.get("script"),
        "sortName": item.get("sortName"),
        # The official v4 format declares both sort-name overrides as text.
        # Treating ``sortNameKeep`` like the neighbouring boolean flags is
        # especially dangerous during whole-glyph lifecycle replay: PyObjC
        # will accept NSNumber/Boolean here, but Glyphs' background serializer
        # later sends ``length`` to the value and crashes.  Source-neutral
        # capture must preserve the schema type before any replay is planned.
        "sortNameKeep": _text(item.get("sortNameKeep")),
        "note": item.get("note", ""),
        "color": _numeric_tree(item.get("color")),
        "locked": _bool(item.get("locked")),
        "direction": CANONICAL_SCHEMA.canonical_value_for_official(
            "definition.glyph", "direction", _number(item.get("direction"))
        ),
        "case": CANONICAL_SCHEMA.canonical_value_for_official(
            "definition.glyph", "case", _number(item.get("case"))
        ),
        "group": item.get("group"),
        "groupIdx": _number(item.get("groupIdx", 0)),
        "leftMetricsKey": _text(item.get("metricLeft")),
        "rightMetricsKey": _text(item.get("metricRight")),
        "widthMetricsKey": _text(item.get("metricWidth")),
        "bottomMetricsKey": _text(item.get("metricBottom")),
        "topMetricsKey": _text(item.get("metricTop")),
        "vertOriginMetricsKey": _text(item.get("metricVertOrigin")),
        "vertWidthMetricsKey": _text(item.get("metricVertWidth")),
        "unicodes": unicodes,
        "tags": [str(value) for value in _sequence(item.get("tags"))],
        "userData": _extension_mapping(item.get("userData")),
        "smartAxes": _generic_records(
            item.get("axes"),
            "smart_axis",
            ("name", "bottomValue", "topValue"),
        ),
        "partsSettings": canonical_extension_value(item.get("partsSettings", [])),
    }
    result.update({canonical: item.get(serialized) for canonical, serialized in aliases.items()})
    return result


def _code_collection(values: Any, root: str) -> list[dict[str, Any]]:
    result = []
    for index, raw in enumerate(_sequence(values)):
        item = _mapping(raw)
        serialized_name = str(item.get("name") or "")
        tag = str(item.get("tag") or serialized_name)
        # Feature identity is its official four-character ``tag``. Classes
        # and prefixes use ``name``.  Treating all three collections alike
        # made a newly serialized feature reappear as ``features_N`` after a
        # verified create, so the next tool call could not address it. Keep
        # the canonical convenience name aligned with the identity while the
        # registry remains the owner of the collection policy.
        name = tag if root == "features" else serialized_name
        identity = tag if root == "features" else name
        result.append(
            {
                "id": identity or "{}_{}".format(root, index),
                "name": name,
                "tag": tag,
                "code": str(item.get("code") or ""),
                "automatic": _bool(item.get("automatic")),
                "disabled": _bool(item.get("disabled")),
                "notes": _text(item.get("notes")),
                "labels": canonical_extension_value(item.get("labels") or []),
            }
        )
    return result


def _merge_package(mapping: Mapping[str, Any]) -> dict[str, Any]:
    package_keys = {"fontinfo.plist", "fontinfo", "order.plist", "kerning.plist"}
    if not package_keys.intersection(mapping):
        # ``SerializedMappingSource`` already owns its boundary copy when the
        # caller requests one. Conversion below is functional: it mutates only
        # this shallow root dictionary and constructs every canonical child
        # anew. Deep-copying a complete flat font here duplicated that work,
        # including every path node, and dominated live read-back time.
        return dict(mapping)
    fontinfo = _mapping(mapping.get("fontinfo.plist") or mapping.get("fontinfo"))
    glyphs = mapping.get("glyphs")
    if isinstance(glyphs, Mapping):
        fontinfo["glyphs"] = [copy.deepcopy(value) for value in glyphs.values()]
    elif glyphs is not None:
        fontinfo["glyphs"] = copy.deepcopy(_sequence(glyphs))
    kerning = _mapping(mapping.get("kerning.plist"))
    for key in ("kerningLTR", "kerningRTL", "kerningVertical", "kerningContext"):
        if key in kerning:
            fontinfo[key] = kerning[key]
    order = mapping.get("order.plist")
    if isinstance(order, Sequence) and not isinstance(order, (str, bytes)):
        ordered_names = [str(name) for name in order]
        by_name = {
            str(_mapping(value).get("glyphname") or ""): value
            for value in _sequence(fontinfo.get("glyphs"))
        }
        ordered = [by_name[name] for name in ordered_names if name in by_name]
        ordered.extend(value for name, value in by_name.items() if name not in set(ordered_names))
        fontinfo["glyphs"] = ordered
    if "note.md" in mapping:
        fontinfo["note"] = str(mapping.get("note.md") or "")
    return fontinfo


def _serialized_to_canonical(
    mapping: Mapping[str, Any], *, document_path: Any = None
) -> dict[str, Any]:
    source = _merge_package(mapping)
    for key in (".appVersion", ".formatVersion", "DisplayStrings", "UIState.plist"):
        source.pop(key, None)
    axes = _axes(source.get("axes"))
    metrics = _metric_records(source.get("metrics"), "metric")
    stems = _metric_records(source.get("stems"), "stem")
    numbers = _metric_records(source.get("numbers"), "number")
    masters = _masters(
        source.get("fontMaster"),
        axes,
        metric_ids=[str(value.get("id") or "") for value in metrics],
        stem_ids=[str(value.get("id") or "") for value in stems],
        number_ids=[str(value.get("id") or "") for value in numbers],
    )
    master_names = {
        str(master.get("id") or ""): str(master.get("name") or "")
        for master in masters
        if str(master.get("id") or "")
    }
    glyphs = {
        str(_mapping(value).get("glyphname") or ""): canonical_glyph_from_serialized(
            _mapping(value), master_names, document_path=document_path
        )
        for value in _sequence(source.get("glyphs"))
        if str(_mapping(value).get("glyphname") or "")
    }
    properties = _properties(source.get("properties"))
    settings = _extension_mapping(source.get("settings"))
    grid = _number(settings.pop("gridLength", 1))
    grid_subdivision = _number(settings.pop("gridSubDivision", 1))
    for key in (
        "keyboardIncrement",
        "keyboardIncrementBig",
        "keyboardIncrementHuge",
    ):
        if key in settings:
            settings[key] = _number(settings[key])
    for key in (
        "disablesAutomaticAlignment",
        "disablesNiceNames",
        "keepAlternatesTogether",
        "previewRemoveOverlap",
        "snapToObjects",
    ):
        if key in settings:
            settings[key] = _bool(settings[key])
    settings.setdefault("dependencies", {})
    if "fontType" in settings:
        settings["fontType"] = CANONICAL_SCHEMA.canonical_value_for_official(
            "document.settings", "fontType", settings["fontType"]
        )
    return {
        "font": {
            "familyName": _family_name(properties),
            "upm": _number(source.get("unitsPerEm")),
            "versionMajor": _number(source.get("versionMajor")),
            "versionMinor": _number(source.get("versionMinor")),
            "note": source.get("note"),
            "date": _text(source.get("date")),
            "grid": grid,
            "gridSubDivision": grid_subdivision,
            "customParameters": _parameters(source.get("customParameters")),
            "properties": properties,
            "userData": _extension_mapping(source.get("userData")),
        },
        "axes": axes,
        "masters": masters,
        "instances": _instances(source.get("instances"), axes),
        "glyphs": glyphs,
        "glyphOrder": list(glyphs),
        "kerning": {
            "ltr": canonical_kerning_domain(
                _mapping(source.get("kerningLTR")),
                glyph_names=glyphs,
                normalize_value=_number,
            ),
            "rtl": canonical_kerning_domain(
                _mapping(source.get("kerningRTL")),
                glyph_names=glyphs,
                normalize_value=_number,
            ),
            "vertical": canonical_kerning_domain(
                _mapping(source.get("kerningVertical")),
                glyph_names=glyphs,
                normalize_value=_number,
            ),
            "context": _numeric_tree(_mapping(source.get("kerningContext"))),
        },
        "features": _code_collection(source.get("features"), "features"),
        "classes": _code_collection(source.get("classes"), "classes"),
        "featurePrefixes": _code_collection(source.get("featurePrefixes"), "featurePrefixes"),
        "metrics": metrics,
        "stems": stems,
        "numbers": numbers,
        "settings": settings,
    }


@dataclass(frozen=True)
class SerializedMappingSource:
    """Normalize an already-decoded flat or package Glyphs document tree.

    This source port accepts an already-decoded mapping and has no
    ``glyphsLib`` dependency. The Glyphs adapter may decode saved OpenStep
    records through the pinned ``openstep_plist`` parser, while revision
    adapters may use any independently verified decoder; all representations
    still enter the canonical model through this single port.
    """

    mapping: Mapping[str, Any]
    copy_source: bool = True
    document_path: Any = None

    def capture(self) -> Mapping[str, Any]:
        value = (
            copy.deepcopy(dict(self.mapping))
            if self.copy_source
            else dict(self.mapping)
        )
        if "font" in value and isinstance(value.get("glyphs"), Mapping):
            for key in (".appVersion", ".formatVersion", "DisplayStrings", "UIState.plist"):
                value.pop(key, None)
            return value
        return _serialized_to_canonical(value, document_path=self.document_path)


__all__ = [
    "CanonicalSource",
    "LiveGlyphsSource",
    "SerializedMappingSource",
    "canonical_info_property",
    "canonical_image_path",
    "canonical_glyph_from_serialized",
    "canonical_root_from_serialized_records",
]
