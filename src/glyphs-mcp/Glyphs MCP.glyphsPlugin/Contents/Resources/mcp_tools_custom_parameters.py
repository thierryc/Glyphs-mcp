# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Generic, guarded access to font and master custom parameters."""

import json
import math

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import (
    _font_resolution_error,
    _resolve_font_by_index,
    _run_on_main_thread,
    _safe_json,
)


READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

WRITE_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


def _font_payload(font, font_index):
    return {
        "fontIndex": int(font_index),
        "familyName": getattr(font, "familyName", "") or "",
        "filePath": getattr(font, "filepath", None),
    }


def _master_by_id(font, master_id):
    wanted = str(master_id or "")
    for master in list(getattr(font, "masters", []) or []):
        if str(getattr(master, "id", "")) == wanted:
            return master
    return None


def _master_payload(master):
    if master is None:
        return None
    return {
        "id": str(getattr(master, "id", "") or ""),
        "name": str(getattr(master, "name", "") or ""),
    }


def _output_value(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (list, tuple)):
        return [_output_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _output_value(item) for key, item in value.items()}
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return str(value)


def _parameter_records(owner, source):
    parameters = getattr(owner, "customParameters", None)
    if parameters is None:
        return []
    if isinstance(parameters, dict):
        return [
            {
                "name": str(name),
                "value": _output_value(value),
                "active": True,
                "source": source,
                "index": index,
            }
            for index, (name, value) in enumerate(parameters.items())
        ]
    records = []
    try:
        iterator = iter(parameters)
    except TypeError:
        return records
    for index, parameter in enumerate(iterator):
        name = getattr(parameter, "name", None)
        if name is None:
            continue
        records.append(
            {
                "name": str(name),
                "value": _output_value(getattr(parameter, "value", None)),
                "active": bool(getattr(parameter, "active", True)),
                "source": source,
                "index": index,
            }
        )
    return records


def _filters(names, prefix):
    if names is None:
        name_set = None
    elif isinstance(names, (list, tuple, set)):
        name_set = {str(name) for name in names if str(name)}
    else:
        return None, None, "names must be a list of custom-parameter names"
    prefix_value = str(prefix) if prefix is not None else None
    return name_set, prefix_value, None


def _matches(record, name_set, prefix):
    name = record["name"]
    return (name_set is None or name in name_set) and (prefix is None or name.startswith(prefix))


def _duplicates(records, name_set, prefix):
    counts = {}
    source_by_name = {}
    for record in records:
        if not _matches(record, name_set, prefix):
            continue
        key = (record["source"], record["name"])
        counts[key] = counts.get(key, 0) + 1
        source_by_name[key] = record["source"]
    return [
        {"name": name, "source": source_by_name[(source, name)], "count": count}
        for (source, name), count in sorted(counts.items())
        if count > 1
    ]


def _resolve_owner(font, scope, master_id):
    normalized = str(scope or "font").strip().lower()
    if normalized == "font":
        return normalized, font, None, None
    if normalized not in ("master", "effective"):
        return normalized, None, None, {
            "ok": False,
            "error": "scope must be 'font', 'master', or 'effective'",
        }
    if not master_id:
        return normalized, None, None, {
            "ok": False,
            "error": "master_id is required for scope='{}'".format(normalized),
        }
    master = _master_by_id(font, master_id)
    if master is None:
        return normalized, None, None, {
            "ok": False,
            "error": "Master ID '{}' not found".format(master_id),
        }
    return normalized, master, master, None


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
async def get_custom_parameters(
    font_index: int = 0,
    scope: str = "font",
    master_id: str = None,
    names: list = None,
    prefix: str = None,
    include_inactive: bool = False,
) -> str:
    """Read generic font/master custom parameters without changing the font.

    Use scope="effective" with a master ID to apply active master-over-font
    precedence. Repeated records are preserved and reported in ``duplicates``.
    """
    try:
        font, fonts = _resolve_font_by_index(Glyphs, font_index)
        if font is None:
            return _safe_json(_font_resolution_error(font_index, fonts, ok_key="ok"))
        name_set, prefix_value, filter_error = _filters(names, prefix)
        if filter_error:
            return _safe_json({"ok": False, "error": filter_error})
        normalized, owner, master, owner_error = _resolve_owner(font, scope, master_id)
        if owner_error:
            owner_error["font"] = _font_payload(font, font_index)
            return _safe_json(owner_error)

        font_records = _parameter_records(font, "font")
        master_records = _parameter_records(master, "master") if master is not None else []
        combined = font_records + master_records
        duplicate_records = _duplicates(combined, name_set, prefix_value)

        if normalized == "effective":
            effective = {}
            for record in combined:
                if record["active"] and _matches(record, name_set, prefix_value):
                    effective[record["name"]] = dict(record)
            records = list(effective.values())
        else:
            records = [
                record for record in _parameter_records(owner, normalized)
                if _matches(record, name_set, prefix_value)
                and (include_inactive or record["active"])
            ]

        return _safe_json({
            "ok": True,
            "scope": normalized,
            "font": _font_payload(font, font_index),
            "master": _master_payload(master),
            "parameters": records,
            "duplicates": duplicate_records,
        })
    except Exception as error:
        return _safe_json({"ok": False, "error": str(error)})

def _validate_changes(changes):
    if not isinstance(changes, dict) or not changes:
        return None, "changes must be a non-empty object mapping names to values"
    normalized = {}
    for raw_name, value in changes.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            return None, "every custom-parameter name must be a non-empty string"
        name = raw_name.strip()
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError, OverflowError):
            return None, "value for '{}' must be finite JSON-compatible data or null".format(name)
        normalized[name] = value
    return normalized, None


def _records_by_name(records):
    result = {}
    for record in records:
        result.setdefault(record["name"], []).append(record)
    return result


def _raw_parameter_state(parameters, name):
    if isinstance(parameters, dict):
        if name not in parameters:
            return {"exists": False, "value": None, "active": None}
        return {
            "exists": True,
            "value": parameters[name],
            "active": True,
        }

    try:
        matching = [
            parameter
            for parameter in parameters
            if str(getattr(parameter, "name", "")) == name
        ]
    except TypeError:
        matching = []
    if not matching:
        return {"exists": False, "value": None, "active": None}
    parameter = matching[-1]
    return {
        "exists": True,
        "value": getattr(parameter, "value", None),
        "active": bool(getattr(parameter, "active", True)),
    }


def _parameter_state_payload(state):
    return {
        "exists": bool(state["exists"]),
        "value": _output_value(state["value"]) if state["exists"] else None,
        "active": state["active"] if state["exists"] else None,
    }


def _parameter_states_match(actual, expected):
    return _parameter_state_payload(actual) == _parameter_state_payload(expected)


def _set_parameter_active(parameters, name, active):
    if isinstance(parameters, dict) or active is None:
        return
    for parameter in parameters:
        if str(getattr(parameter, "name", "")) == name:
            try:
                parameter.active = bool(active)
            except Exception:
                if bool(getattr(parameter, "active", True)) != bool(active):
                    raise


def _restore_parameter_state(parameters, name, state):
    current = _raw_parameter_state(parameters, name)
    if not state["exists"]:
        if current["exists"]:
            del parameters[name]
        return
    parameters[name] = state["value"]
    _set_parameter_active(parameters, name, state["active"])


def _custom_parameter_mutation_outcome(owner, source, changes, redraw):
    parameters = owner.customParameters
    originals = {
        name: _raw_parameter_state(parameters, name)
        for name in changes
    }
    written = []

    try:
        for name, value in changes.items():
            if value is None:
                if originals[name]["exists"]:
                    del parameters[name]
                    written.append(name)
            else:
                parameters[name] = value
                written.append(name)

        mismatches = []
        for name, value in changes.items():
            original = originals[name]
            expected = (
                {"exists": False, "value": None, "active": None}
                if value is None
                else {
                    "exists": True,
                    "value": value,
                    "active": original["active"] if original["exists"] else True,
                }
            )
            actual = _raw_parameter_state(parameters, name)
            if not _parameter_states_match(actual, expected):
                mismatches.append({
                    "parameterName": name,
                    "expected": _parameter_state_payload(expected),
                    "actual": _parameter_state_payload(actual),
                })
        if mismatches:
            raise RuntimeError(
                "Custom-parameter verification failed: {}".format(
                    json.dumps(mismatches, sort_keys=True)
                )
            )

        if callable(redraw):
            redraw()
        return {
            "ok": True,
            "writtenParameterNames": written,
            "verifiedParameterNames": list(changes),
            "readback": [
                record
                for record in _parameter_records(owner, source)
                if record["name"] in changes
            ],
            "rollback": None,
        }
    except Exception as exc:
        rollback_errors = []
        for name in reversed(list(changes)):
            try:
                _restore_parameter_state(parameters, name, originals[name])
            except Exception as rollback_exc:
                rollback_errors.append({
                    "parameterName": name,
                    "message": str(rollback_exc),
                })

        for name in changes:
            try:
                actual = _raw_parameter_state(parameters, name)
            except Exception as verify_exc:
                rollback_errors.append({
                    "parameterName": name,
                    "message": "Rollback read-back failed: {}".format(verify_exc),
                })
                continue
            if not _parameter_states_match(actual, originals[name]):
                rollback_errors.append({
                    "parameterName": name,
                    "expected": _parameter_state_payload(originals[name]),
                    "actual": _parameter_state_payload(actual),
                    "message": "Rollback verification mismatch.",
                })

        if callable(redraw):
            try:
                redraw()
            except Exception as redraw_exc:
                rollback_errors.append({
                    "stage": "redraw",
                    "message": str(redraw_exc),
                })

        return {
            "ok": False,
            "error": str(exc),
            "writtenParameterNames": written,
            "verifiedParameterNames": [],
            "readback": [
                record
                for record in _parameter_records(owner, source)
                if record["name"] in changes
            ],
            "rollback": {
                "attempted": True,
                "succeeded": not rollback_errors,
                "errors": rollback_errors,
            },
        }


@mcp.tool(annotations=WRITE_ANNOTATIONS)
async def set_custom_parameters(
    font_index: int = 0,
    scope: str = "font",
    master_id: str = None,
    changes: dict = None,
    dry_run: bool = True,
    confirm: bool = False,
) -> str:
    """Preview or apply generic custom-parameter changes without saving.

    A JSON ``null`` value deletes a parameter. Mutation requires both
    ``dry_run=false`` and ``confirm=true``. Targeted duplicate names are
    rejected because updating an ambiguous record could lose information.
    """
    try:
        font, fonts = _resolve_font_by_index(Glyphs, font_index)
        if font is None:
            return _safe_json(_font_resolution_error(font_index, fonts, ok_key="ok"))
        normalized_scope = str(scope or "font").strip().lower()
        if normalized_scope not in ("font", "master"):
            return _safe_json({
                "ok": False,
                "error": "scope must be 'font' or 'master' for writes",
            })
        _scope, owner, master, owner_error = _resolve_owner(font, normalized_scope, master_id)
        if owner_error:
            owner_error["font"] = _font_payload(font, font_index)
            return _safe_json(owner_error)
        normalized_changes, change_error = _validate_changes(changes)
        if change_error:
            return _safe_json({"ok": False, "error": change_error})

        before_records = _parameter_records(owner, normalized_scope)
        by_name = _records_by_name(before_records)
        duplicate_names = sorted(
            name for name in normalized_changes if len(by_name.get(name, [])) > 1
        )
        if duplicate_names:
            return _safe_json({
                "ok": False,
                "error": "Refusing to change duplicate custom parameters: {}".format(
                    ", ".join(duplicate_names)
                ),
                "duplicates": duplicate_names,
            })

        preview = []
        for name, value in normalized_changes.items():
            existing = by_name.get(name, [])
            before = existing[0]["value"] if existing else None
            if value is None:
                action = "delete" if existing else "noop"
            else:
                action = "update" if existing else "create"
            preview.append({
                "name": name,
                "action": action,
                "before": before,
                "after": _output_value(value),
            })

        base_payload = {
            "scope": normalized_scope,
            "font": _font_payload(font, font_index),
            "master": _master_payload(master),
            "dryRun": bool(dry_run),
            "confirmed": bool(confirm),
            "changes": preview,
        }
        if dry_run:
            base_payload.update({"ok": True, "applied": False})
            return _safe_json(base_payload)
        if not confirm:
            base_payload.update({
                "ok": False,
                "applied": False,
                "error": "confirm=true is required when dry_run=false",
            })
            return _safe_json(base_payload)

        redraw = getattr(Glyphs, "redraw", None)
        outcome = _run_on_main_thread(
            lambda: _custom_parameter_mutation_outcome(
                owner,
                normalized_scope,
                normalized_changes,
                redraw,
            )
        )
        base_payload.update({
            "ok": bool(outcome.get("ok")),
            "applied": bool(outcome.get("ok")),
            "readback": outcome.get("readback", []),
            "saved": False,
            "writtenParameterNames": outcome.get("writtenParameterNames", []),
            "verifiedParameterNames": outcome.get("verifiedParameterNames", []),
            "rollback": outcome.get("rollback"),
        })
        if not outcome.get("ok"):
            base_payload["error"] = (
                outcome.get("error")
                or "Custom-parameter mutation failed."
            )
        return _safe_json(base_payload)
    except Exception as error:
        return _safe_json({"ok": False, "error": str(error)})
