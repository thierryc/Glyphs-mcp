# encoding: utf-8

"""Host-independent LitSquare metadata contract and presentation helpers."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import re
from collections import OrderedDict
from datetime import datetime, timezone


ROOT_KEY = "com.litsquare"
ROLE_KEY = "com.litsquare.role"
SCHEMA_VERSION = 1
UPDATED_AT_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)

KNOWN_FIELD_ORDER = (
    "schemaVersion",
    "updatedAt",
    "settings",
    "memory",
    "status",
    "notes",
)

# Suggested semantics for common roles. This mapping is descriptive, not an allowlist.
ROLE_INFO = OrderedDict(
    (
        ("body", "Main visible form of a glyph or icon."),
        ("detail", "Secondary visible detail within the design."),
        ("counter", "Intentional enclosed negative-space contour in a regular glyph."),
        ("cutout", "Shape intended to subtract or knock out another shape."),
        ("accent", "Diacritic, dot, or independent emphasis shape."),
        ("connector", "Shape that joins or bridges other forms."),
        ("container", "Enclosing icon shape such as a circle, shield, or capsule."),
        ("badge", "Status badge or small overlay attached to an icon."),
        ("foreground", "Visible shape intentionally placed above the main form."),
        ("background", "Supporting visible shape intentionally placed behind the main form."),
        ("helper", "Construction shape retained for processing, not final semantic artwork."),
        ("reference", "Alignment or measurement reference for an automated workflow."),
        ("erase", "SF Symbols-compatible semantic erase role; does not set Glyphs mask."),
        ("hidden", "Semantic rendering exclusion; distinct from Glyphs' hidden attribute."),
    )
)
ROLES = tuple(ROLE_INFO)
MIGRATIONS = {}


def _mapping_items(value):
    if isinstance(value, dict):
        return list(value.items())
    try:
        return list(value.items())
    except Exception:
        pass
    try:
        return [(key, value[key]) for key in value.keys()]
    except Exception:
        return None


def _sequence_items(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, (str, bytes, bytearray, memoryview)):
        return None
    class_name = value.__class__.__name__ if value is not None else ""
    if class_name not in {"NSArray", "NSMutableArray", "__NSArrayI", "__NSArrayM"}:
        return None
    try:
        return list(value)
    except Exception:
        try:
            return [value[index] for index in range(len(value))]
        except Exception:
            return None


def _binary_bytes(value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    class_name = value.__class__.__name__ if value is not None else ""
    if "Data" not in class_name:
        return None
    try:
        return bytes(value)
    except Exception:
        pass
    try:
        length = int(value.length())
        pointer = value.bytes()
        return bytes(pointer.as_buffer(length))
    except Exception:
        return None


def to_plain(value, path="$", errors=None):
    """Convert Foundation/Python plist values to detached Python values."""

    if errors is None:
        errors = []
    if value is None:
        errors.append({"path": path, "code": "null_not_allowed", "message": "Null is not property-list-compatible for LitSquare metadata."})
        return None
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            errors.append({"path": path, "code": "non_finite_number", "message": "Numbers must be finite."})
        return float(value)
    if isinstance(value, str):
        return str(value)

    binary = _binary_bytes(value)
    if binary is not None:
        return binary

    mapping = _mapping_items(value)
    if mapping is not None:
        out = {}
        for key, item in mapping:
            if not isinstance(key, str):
                errors.append({"path": path, "code": "non_string_key", "message": "Dictionary keys must be strings."})
                continue
            out[str(key)] = to_plain(item, path + "." + str(key), errors)
        return out

    sequence = _sequence_items(value)
    if sequence is not None:
        return [to_plain(item, "{}[{}]".format(path, index), errors) for index, item in enumerate(sequence)]

    errors.append({
        "path": path,
        "code": "unsupported_type",
        "message": "Unsupported value type: {}.".format(value.__class__.__name__),
    })
    return None


def _validate_known_fields(value, errors, warnings):
    version = value.get("schemaVersion")
    if type(version) is not int or version < 1:
        errors.append({"path": "$.schemaVersion", "code": "invalid_schema_version", "message": "schemaVersion must be a positive integer."})

    updated_at = value.get("updatedAt")
    if not _valid_updated_at(updated_at):
        errors.append({"path": "$.updatedAt", "code": "invalid_updated_at", "message": "updatedAt must be an RFC 3339 UTC string ending in Z."})

    for field in ("settings", "memory", "status"):
        if field in value and not isinstance(value[field], dict):
            errors.append({"path": "$." + field, "code": "invalid_field_type", "message": "{} must be a dictionary.".format(field)})

    if "notes" in value:
        notes = value["notes"]
        if not isinstance(notes, list):
            errors.append({"path": "$.notes", "code": "invalid_field_type", "message": "notes must be an array."})
        else:
            for index, note in enumerate(notes):
                note_path = "$.notes[{}]".format(index)
                if not isinstance(note, dict):
                    errors.append({"path": note_path, "code": "invalid_note", "message": "Each note must be a dictionary."})
                    continue
                for required in ("id", "text"):
                    if not isinstance(note.get(required), str) or not note.get(required):
                        errors.append({"path": note_path + "." + required, "code": "invalid_note", "message": "Note {} must be a non-empty string.".format(required)})
                for optional in ("createdAt", "updatedAt", "author"):
                    if optional in note and not isinstance(note[optional], str):
                        errors.append({"path": note_path + "." + optional, "code": "invalid_note", "message": "Note {} must be a string.".format(optional)})



def _valid_updated_at(value):
    if not isinstance(value, str) or not UPDATED_AT_PATTERN.match(value):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
        return True
    except (TypeError, ValueError):
        return False


def validate_metadata(raw, present=True):
    """Return a stable inspector state and detached native value."""

    if not present:
        return {
            "state": "missing",
            "label": "Missing",
            "schemaVersion": None,
            "updatedAt": None,
            "value": None,
            "errors": [],
            "warnings": [],
        }

    errors = []
    plain = to_plain(raw, errors=errors)
    if not isinstance(plain, dict):
        if not errors:
            errors.append({"path": "$", "code": "invalid_root", "message": "The LitSquare root must be a dictionary."})
        return {
            "state": "invalid",
            "label": "Invalid",
            "schemaVersion": None,
            "updatedAt": None,
            "value": plain,
            "errors": errors,
            "warnings": [],
        }
    if not plain:
        return {
            "state": "empty",
            "label": "Empty",
            "schemaVersion": None,
            "updatedAt": None,
            "value": {},
            "errors": errors,
            "warnings": [],
        }

    version = plain.get("schemaVersion")
    warnings = []
    if type(version) is int and version > SCHEMA_VERSION:
        warnings.append({
            "path": "$.schemaVersion",
            "code": "unsupported_schema",
            "message": "Schema version {} is newer than supported version {}.".format(version, SCHEMA_VERSION),
        })
        return {
            "state": "unsupported_schema",
            "label": "Unsupported schema",
            "schemaVersion": version,
            "updatedAt": plain.get("updatedAt") if isinstance(plain.get("updatedAt"), str) else None,
            "value": plain,
            "errors": [],
            "warnings": warnings,
        }
    _validate_known_fields(plain, errors, warnings)
    if errors:
        state, label = "invalid", "Invalid"
    elif warnings:
        state, label = "valid_with_warnings", "Valid with warnings"
    else:
        state, label = "valid", "Valid v{}".format(version)
    return {
        "state": state,
        "label": label,
        "schemaVersion": version if isinstance(version, int) else None,
        "updatedAt": plain.get("updatedAt") if isinstance(plain.get("updatedAt"), str) else None,
        "value": plain,
        "errors": errors,
        "warnings": warnings,
    }


def _json_value(value, prefer_known=False):
    if isinstance(value, bytes):
        return {"$binary": {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}}
    if isinstance(value, dict):
        ordered = OrderedDict()
        preferred = KNOWN_FIELD_ORDER if prefer_known else ()
        for key in preferred:
            if key in value:
                ordered[key] = _json_value(value[key], prefer_known=False)
        for key in sorted(key for key in value if key not in preferred):
            ordered[key] = _json_value(value[key], prefer_known=False)
        return ordered
    if isinstance(value, list):
        return [_json_value(item, prefer_known=False) for item in value]
    return value


def canonical_json(value):
    prefer_known = isinstance(value, dict) and "schemaVersion" in value
    return json.dumps(_json_value(value, prefer_known=prefer_known), indent=2, ensure_ascii=False) + "\n"


def json_safe(value):
    """Return JSON-transport-safe data while preserving binary type markers."""

    return json.loads(json.dumps(_json_value(value, prefer_known=False), ensure_ascii=False))


def _native_description(value):
    try:
        description = str(value)
    except Exception:
        description = ""
    if len(description) > 1000:
        description = description[:999] + "…"
    return description


def _native_date_string(value):
    instant = None
    if isinstance(value, datetime):
        instant = value
    else:
        class_name = value.__class__.__name__ if value is not None else ""
        interval = getattr(value, "timeIntervalSince1970", None)
        if "Date" in class_name and callable(interval):
            try:
                instant = datetime.fromtimestamp(float(interval()), tz=timezone.utc)
            except Exception:
                instant = None
    if instant is None:
        return None
    if instant.tzinfo is None:
        return instant.isoformat()
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def native_inspection_projection(value):
    """Detach arbitrary native metadata into a read-only JSON projection.

    This intentionally accepts more native property-list types than the
    editable LitSquare contract. Values that JSON cannot represent directly
    receive presentation-only markers and warnings; nothing is discarded or
    converted back for persistence.
    """

    warnings = []
    active = set()

    def project(item, path):
        if item is None:
            warnings.append(
                {
                    "path": path,
                    "code": "native_null",
                    "message": "Native null is represented by a diagnostic marker.",
                }
            )
            return {"$nativeObject": {"type": "NoneType", "description": "null"}}
        if isinstance(item, bool):
            return bool(item)
        if isinstance(item, int):
            return int(item)
        if isinstance(item, float):
            if math.isfinite(item):
                return float(item)
            warnings.append(
                {
                    "path": path,
                    "code": "non_finite_number",
                    "message": "A non-finite number is represented by a diagnostic marker.",
                }
            )
            return {
                "$nativeObject": {
                    "type": "float",
                    "description": _native_description(item),
                }
            }
        if isinstance(item, str):
            return str(item)

        binary = _binary_bytes(item)
        if binary is not None:
            return {
                "$binary": {
                    "encoding": "base64",
                    "data": base64.b64encode(binary).decode("ascii"),
                }
            }

        date_text = _native_date_string(item)
        if date_text is not None:
            return {"$date": date_text}

        mapping = _mapping_items(item)
        if mapping is not None:
            identity = id(item)
            if identity in active:
                warnings.append(
                    {
                        "path": path,
                        "code": "recursive_value",
                        "message": "A recursive dictionary is represented by a diagnostic marker.",
                    }
                )
                return {
                    "$nativeObject": {
                        "type": item.__class__.__name__,
                        "description": "recursive value",
                    }
                }
            active.add(identity)
            try:
                if all(isinstance(key, str) for key, _child in mapping):
                    return {
                        str(key): project(child, path + "." + str(key))
                        for key, child in mapping
                    }
                warnings.append(
                    {
                        "path": path,
                        "code": "non_string_key",
                        "message": "A native dictionary with non-string keys uses an entry-list marker.",
                    }
                )
                return {
                    "$nativeDictionary": [
                        {
                            "key": project(key, "{}.$key[{}]".format(path, index)),
                            "value": project(
                                child, "{}.$value[{}]".format(path, index)
                            ),
                        }
                        for index, (key, child) in enumerate(mapping)
                    ]
                }
            finally:
                active.remove(identity)

        sequence = _sequence_items(item)
        if sequence is not None:
            identity = id(item)
            if identity in active:
                warnings.append(
                    {
                        "path": path,
                        "code": "recursive_value",
                        "message": "A recursive array is represented by a diagnostic marker.",
                    }
                )
                return {
                    "$nativeObject": {
                        "type": item.__class__.__name__,
                        "description": "recursive value",
                    }
                }
            active.add(identity)
            try:
                return [
                    project(child, "{}[{}]".format(path, index))
                    for index, child in enumerate(sequence)
                ]
            finally:
                active.remove(identity)

        class_name = item.__class__.__name__
        warnings.append(
            {
                "path": path,
                "code": "unsupported_native_object",
                "message": "A native {} object uses a diagnostic marker.".format(
                    class_name
                ),
            }
        )
        return {
            "$nativeObject": {
                "type": class_name,
                "description": _native_description(item),
            }
        }

    return {"value": project(value, "$"), "warnings": warnings}


def from_json_projection(value):
    """Decode JSON transport markers without persisting marker dictionaries."""

    if isinstance(value, dict):
        if set(value) == {"$binary"} and isinstance(value.get("$binary"), dict):
            marker = value["$binary"]
            if set(marker) != {"encoding", "data"} or marker.get("encoding") != "base64":
                raise ValueError("Invalid LitSquare binary projection marker.")
            data = marker.get("data")
            if not isinstance(data, str):
                raise ValueError("LitSquare binary projection data must be a base64 string.")
            try:
                return base64.b64decode(data.encode("ascii"), validate=True)
            except Exception as exc:
                raise ValueError("Invalid base64 data in LitSquare binary projection.") from exc
        return {key: from_json_projection(item) for key, item in value.items()}
    if isinstance(value, list):
        return [from_json_projection(item) for item in value]
    return value


def parse_metadata_json(text):
    """Parse the editable JSON projection and require a compatible root object."""

    if not isinstance(text, str):
        raise ValueError("Invalid input: metadata must be JSON text.")
    try:
        projected = json.loads(text)
    except Exception as exc:
        raise ValueError("Invalid input: enter a JSON object.") from exc
    if not isinstance(projected, dict):
        raise ValueError("Invalid input: the LitSquare root must be a JSON object.")
    try:
        native = from_json_projection(projected)
    except ValueError as exc:
        raise ValueError("Invalid input: {}".format(exc)) from exc
    validation = validate_metadata(native, present=True)
    if validation["state"] == "unsupported_schema":
        raise ValueError("Invalid input: unsupported schema version.")
    if validation["state"] not in {"empty", "valid", "valid_with_warnings"}:
        raise ValueError("Invalid input: metadata is not valid LitSquare data.")
    if native and native.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("Invalid input: schemaVersion must be 1.")
    return native, validation


def parse_path_role_json(text):
    """Parse the Palette projection for the `com.litsquare.role` domain."""

    if not isinstance(text, str):
        raise ValueError("Invalid input: path role must be JSON text.")
    if not text.strip():
        return None
    try:
        projected = json.loads(text)
    except Exception as exc:
        raise ValueError("Invalid input: enter a JSON object.") from exc
    if not isinstance(projected, dict) or set(projected) - {"role"}:
        raise ValueError("Invalid input: path metadata must contain only role.")
    if "role" not in projected or projected.get("role") is None:
        return None
    role = projected.get("role")
    if not isinstance(role, str) or not role.strip():
        raise ValueError("Invalid input: role must be a non-empty string.")
    return role.strip()


def migrate_metadata(raw, target_version=SCHEMA_VERSION, migrations=None, updated_at=None):
    """Run an explicit sequential migration and preserve unrecognized fields.

    No migration is registered for schema v1 today. Callers introducing a
    future schema must supply or register one function for every version step.
    Ordinary reads and merge patches never call this function.
    """

    errors = []
    value = to_plain(raw, errors=errors)
    if errors or not isinstance(value, dict) or not value:
        raise ValueError("Only non-empty property-list-compatible metadata can be migrated.")
    version = value.get("schemaVersion")
    if type(version) is not int or version < 1:
        raise ValueError("A positive integer schemaVersion is required for migration.")
    if type(target_version) is not int or target_version < version:
        raise ValueError("target_version must be an integer at least as new as the source schema.")
    steps = MIGRATIONS if migrations is None else migrations
    migrated = copy.deepcopy(value)
    if version < target_version and not _valid_updated_at(updated_at):
        raise ValueError("An explicit RFC 3339 updated_at is required for migration.")
    while version < target_version:
        migration = steps.get(version) if isinstance(steps, dict) else None
        if not callable(migration):
            raise ValueError("No LitSquare migration is registered for schema {} to {}.".format(version, version + 1))
        result = migration(copy.deepcopy(migrated))
        if not isinstance(result, dict):
            raise ValueError("A LitSquare migration must return a dictionary.")
        migrated = result
        version += 1
        migrated["schemaVersion"] = version
        migrated["updatedAt"] = updated_at
        validation_errors = []
        to_plain(migrated, errors=validation_errors)
        if validation_errors:
            raise ValueError("Migration produced non-property-list-compatible data.")
    return migrated


def merge_patch(document, patch):
    """Apply RFC 7396 JSON Merge Patch semantics to detached values."""

    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    target = copy.deepcopy(document) if isinstance(document, dict) else {}
    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, dict):
            target[key] = merge_patch(target.get(key), value)
        else:
            target[key] = copy.deepcopy(value)
    return target


def effective_settings(scopes):
    """Overlay settings in Font, Glyph, Layer order and retain provenance."""

    values = {}
    provenance = {}
    for scope_name in ("font", "glyph", "layer"):
        result = scopes.get(scope_name) or {}
        root = result.get("value") if isinstance(result, dict) else None
        settings = root.get("settings") if isinstance(root, dict) else None
        if not isinstance(settings, dict):
            continue
        for key, value in settings.items():
            values[key] = copy.deepcopy(value)
            provenance[key] = scope_name
    return {"values": values, "provenance": provenance}


def normalize_role(raw, present=True):
    if not present:
        return {"state": "unassigned", "role": None, "label": "unassigned", "description": "No semantic role is assigned."}
    if not isinstance(raw, str) or not raw.strip():
        try:
            raw_value = json_safe(raw)
        except Exception:
            raw_value = {"$invalidType": raw.__class__.__name__}
        return {
            "state": "invalid",
            "role": None,
            "label": "Invalid",
            "description": "The stored role must be a non-empty string.",
            "raw": raw_value,
        }
    role = raw.strip()
    return {
        "state": "valid",
        "role": role,
        "label": role,
        "description": ROLE_INFO.get(role, "Custom semantic path role."),
    }


def normalize_role_input(value):
    """Normalize a role write; an empty trimmed string removes the role."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("role must be a string or null.")
    return value.strip() or None


def aggregate_roles(entries):
    counts = OrderedDict()
    normalized = []
    identities = []
    for entry in entries:
        result = normalize_role(entry.get("rawRole"), entry.get("rolePresent", False))
        normalized.append(result)
        if result["state"] == "invalid":
            raw_identity = json.dumps(result.get("raw"), sort_keys=True, separators=(",", ":"))
            identities.append(("invalid", raw_identity))
        else:
            identities.append((result["state"], result.get("role")))
        key = result["role"] if result["state"] == "valid" else result["state"]
        counts[key] = counts.get(key, 0) + 1
    shared = identities[0] if identities and all(item == identities[0] for item in identities) else None
    if not identities:
        label = "No selected paths"
        state = "no_context"
    elif shared is not None:
        label = normalized[0]["label"]
        state = normalized[0]["state"]
    else:
        label = "Mixed"
        state = "mixed"
    description = normalized[0]["description"] if shared is not None else "Selected paths have different semantic roles."
    return {
        "state": state,
        "label": label,
        "sharedRole": normalized[0].get("role") if shared is not None else None,
        "description": description,
        "counts": dict(counts),
        "selectedPathCount": len(entries),
    }


def role_field_presentation(aggregation):
    """Build the host-independent value/placeholder model for the Palette field."""

    aggregation = aggregation if isinstance(aggregation, dict) else {}
    count = int(aggregation.get("selectedPathCount", 0) or 0)
    state = str(aggregation.get("state") or "no_context")
    value = ""
    placeholder = ""
    copy_value = ""
    warning = False
    if count <= 0:
        enabled = False
    elif state == "valid":
        enabled = True
        value = str(aggregation.get("sharedRole") or "")
        copy_value = value
    elif state == "unassigned":
        enabled = True
    elif state == "mixed":
        enabled = True
        placeholder = "mixed"
        copy_value = "mixed"
    else:
        enabled = True
        placeholder = "invalid"
        copy_value = "invalid"
        warning = True
    return {
        "enabled": enabled,
        "value": value,
        "placeholder": placeholder,
        "copyValue": copy_value,
        "warning": warning,
    }


def path_fingerprint(path_record):
    payload = json.dumps(path_record, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "KNOWN_FIELD_ORDER",
    "ROLE_INFO",
    "ROLE_KEY",
    "ROLES",
    "ROOT_KEY",
    "SCHEMA_VERSION",
    "aggregate_roles",
    "canonical_json",
    "effective_settings",
    "from_json_projection",
    "json_safe",
    "merge_patch",
    "migrate_metadata",
    "native_inspection_projection",
    "normalize_role",
    "normalize_role_input",
    "parse_metadata_json",
    "parse_path_role_json",
    "path_fingerprint",
    "role_field_presentation",
    "to_plain",
    "validate_metadata",
]
