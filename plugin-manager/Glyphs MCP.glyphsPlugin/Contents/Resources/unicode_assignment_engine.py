# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Pure helpers for reviewing and applying Unicode assignments.

This module deliberately has no GlyphsApp dependency.  It operates on plain
glyph records so allocation, comparison, and preflight behavior can be tested
outside Glyphs.
"""

import re


UNICODE_MAX = 0x10FFFF
BMP_PUA_START = 0xE000
BMP_PUA_END = 0xF8FF
SUPPLEMENTARY_PUA_A_START = 0xF0000
SUPPLEMENTARY_PUA_A_END = 0xFFFFD
SUPPLEMENTARY_PUA_B_START = 0x100000
SUPPLEMENTARY_PUA_B_END = 0x10FFFD

_HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")
_PUA_RANGES = (
    (BMP_PUA_START, BMP_PUA_END),
    (SUPPLEMENTARY_PUA_A_START, SUPPLEMENTARY_PUA_A_END),
    (SUPPLEMENTARY_PUA_B_START, SUPPLEMENTARY_PUA_B_END),
)


def is_surrogate(codepoint):
    return 0xD800 <= int(codepoint) <= 0xDFFF


def is_noncharacter(codepoint):
    value = int(codepoint)
    return 0xFDD0 <= value <= 0xFDEF or (value & 0xFFFE) == 0xFFFE


def is_private_use(codepoint):
    value = int(codepoint)
    return any(start <= value <= end for start, end in _PUA_RANGES)


def classify_codepoint(codepoint):
    value = parse_codepoint(codepoint)
    if is_private_use(value):
        return "private_use"
    if is_noncharacter(value):
        return "noncharacter"
    return "standard"


def format_codepoint(codepoint):
    return "{:04X}".format(int(codepoint))


def parse_codepoint(value):
    """Parse one Unicode scalar value and return its integer codepoint."""
    if isinstance(value, bool):
        raise ValueError("Boolean values are not Unicode codepoints")

    if isinstance(value, int):
        codepoint = value
    else:
        try:
            text = str(value).strip()
        except Exception:
            raise ValueError("Unicode codepoint must be an integer or hexadecimal string")
        if text.upper().startswith("U+"):
            text = text[2:]
        elif text.lower().startswith("0x"):
            text = text[2:]
        if not text or not _HEX_RE.match(text):
            raise ValueError("Invalid hexadecimal Unicode codepoint: {!r}".format(value))
        codepoint = int(text, 16)

    if codepoint < 0 or codepoint > UNICODE_MAX:
        raise ValueError("Unicode codepoint is outside 0000-10FFFF: {!r}".format(value))
    if is_surrogate(codepoint):
        raise ValueError("Surrogate codepoints are not Unicode scalar values: {}".format(format_codepoint(codepoint)))
    return codepoint


def normalize_codepoint(value):
    return format_codepoint(parse_codepoint(value))


def _as_values(raw):
    if raw is None:
        return []
    if isinstance(raw, (str, int)):
        return [raw]
    try:
        return list(raw)
    except Exception:
        return [raw]


def _normalize_values(raw, field_name, reject_duplicates=False):
    normalized = []
    errors = []
    seen = set()
    for item in _as_values(raw):
        try:
            value = normalize_codepoint(item)
        except ValueError as exc:
            errors.append(
                {
                    "code": "invalid_unicode",
                    "field": field_name,
                    "value": repr(item),
                    "message": str(exc),
                }
            )
            continue
        if value in seen:
            if reject_duplicates:
                errors.append(
                    {
                        "code": "duplicate_unicode_in_assignment",
                        "field": field_name,
                        "codepoint": value,
                        "message": "Unicode assignment lists must not contain duplicate values.",
                    }
                )
            continue
        seen.add(value)
        normalized.append(value)
    return normalized, errors


def normalize_codepoints(raw):
    values, errors = _normalize_values(raw, "unicodes", reject_duplicates=True)
    if errors:
        raise ValueError(errors[0]["message"])
    return values


def _normalize_glyph_records(glyphs):
    records = {}
    errors = []
    for index, raw in enumerate(list(glyphs or [])):
        if not isinstance(raw, dict):
            raise ValueError("Glyph record {} must be an object".format(index))
        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValueError("Glyph record {} has no name".format(index))
        if name in records:
            raise ValueError("Duplicate glyph record: {}".format(name))
        values, value_errors = _normalize_values(
            raw.get("unicodes"),
            "glyphs.{}.unicodes".format(name),
            reject_duplicates=True,
        )
        for item in value_errors:
            item["glyphName"] = name
        errors.extend(value_errors)
        records[name] = {
            "name": name,
            "unicodes": values,
            "export": bool(raw.get("export", True)),
            "invalidUnicodeCount": len(value_errors),
        }
    return records, errors


def _normalize_previous_map(previous_map):
    if previous_map is None:
        return {}
    if not isinstance(previous_map, dict):
        raise ValueError("previous_map must be an object mapping glyph names to Unicode lists")
    normalized = {}
    for raw_name, raw_values in previous_map.items():
        name = str(raw_name or "").strip()
        if not name:
            raise ValueError("previous_map contains an empty glyph name")
        values, errors = _normalize_values(
            raw_values,
            "previous_map.{}".format(name),
            reject_duplicates=True,
        )
        if errors:
            raise ValueError(errors[0]["message"])
        normalized[name] = values
    return normalized


def _normalize_reserved(reserved_codepoints):
    values, errors = _normalize_values(
        reserved_codepoints,
        "reserved_codepoints",
        reject_duplicates=False,
    )
    if errors:
        raise ValueError(errors[0]["message"])
    return set(values)


def _range_is_private_use(start, end):
    return any(range_start <= start <= end <= range_end for range_start, range_end in _PUA_RANGES)


def _iter_assignable_range(start, end, direction):
    if direction == "ascending":
        values = range(start, end + 1)
    else:
        values = range(end, start - 1, -1)
    for value in values:
        if is_surrogate(value) or is_noncharacter(value):
            continue
        yield format_codepoint(value)


def _duplicate_findings(records):
    by_codepoint = {}
    for record in records.values():
        for value in record["unicodes"]:
            by_codepoint.setdefault(value, []).append(record)

    errors = []
    warnings = []
    for codepoint, owners in sorted(by_codepoint.items()):
        if len(owners) < 2:
            continue
        exporting = sorted(record["name"] for record in owners if record["export"])
        all_names = sorted(record["name"] for record in owners)
        finding = {
            "code": "duplicate_unicode",
            "codepoint": codepoint,
            "glyphNames": all_names,
            "exportingGlyphNames": exporting,
            "message": "{} is assigned to multiple glyphs.".format(codepoint),
        }
        if len(exporting) >= 2:
            errors.append(finding)
        else:
            warnings.append(finding)
    return errors, warnings


def _previous_map_changes(records, previous):
    current_map = {name: list(record["unicodes"]) for name, record in records.items()}
    unchanged = []
    changed = []
    removed = []
    added = []

    for name in sorted(previous):
        old_values = previous[name]
        if name not in current_map:
            removed.append({"glyphName": name, "previousUnicodes": list(old_values)})
            continue
        current_values = current_map[name]
        if current_values == old_values:
            unchanged.append({"glyphName": name, "unicodes": list(current_values)})
        else:
            changed.append(
                {
                    "glyphName": name,
                    "previousUnicodes": list(old_values),
                    "currentUnicodes": list(current_values),
                }
            )

    for name in sorted(set(current_map).difference(previous)):
        if current_map[name]:
            added.append({"glyphName": name, "unicodes": list(current_map[name])})

    return {
        "previousMapProvided": bool(previous),
        "unchanged": unchanged,
        "changed": changed,
        "removed": removed,
        "added": added,
    }


def review_assignments(
    glyphs,
    target_names,
    allocate_unencoded=False,
    range_start="E000",
    range_end="F8FF",
    direction="ascending",
    reserved_codepoints=None,
    previous_map=None,
):
    """Review current mappings and optionally propose deterministic assignments."""
    records, errors = _normalize_glyph_records(glyphs)
    warnings = []

    names = []
    seen_names = set()
    for raw_name in list(target_names or []):
        name = str(raw_name or "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        names.append(name)
    names = sorted(names)

    for name in names:
        if name not in records:
            errors.append(
                {
                    "code": "glyph_not_found",
                    "glyphName": name,
                    "message": "Glyph '{}' was not found.".format(name),
                }
            )

    direction_value = str(direction or "").strip().lower()
    if direction_value not in ("ascending", "descending"):
        raise ValueError("direction must be 'ascending' or 'descending'")

    start = parse_codepoint(range_start)
    end = parse_codepoint(range_end)
    if start > end:
        raise ValueError("range_start must be less than or equal to range_end")

    previous = _normalize_previous_map(previous_map)
    explicit_reserved = _normalize_reserved(reserved_codepoints)
    previous_reserved = set()
    for values in previous.values():
        previous_reserved.update(values)
    reserved = explicit_reserved.union(previous_reserved)

    duplicate_errors, duplicate_warnings = _duplicate_findings(records)
    errors.extend(duplicate_errors)
    warnings.extend(duplicate_warnings)

    target_records = [records[name] for name in names if name in records]
    for record in target_records:
        if record["export"] and not record["unicodes"] and not record["invalidUnicodeCount"]:
            warnings.append(
                {
                    "code": "exporting_glyph_unencoded",
                    "glyphName": record["name"],
                    "message": "Exporting target glyph has no Unicode assignment.",
                }
            )
        if not record["export"] and record["unicodes"]:
            warnings.append(
                {
                    "code": "non_exporting_glyph_encoded",
                    "glyphName": record["name"],
                    "unicodes": list(record["unicodes"]),
                    "message": "Non-exporting target glyph has Unicode assignments.",
                }
            )
        if len(record["unicodes"]) > 1:
            warnings.append(
                {
                    "code": "multiple_unicode_assignments",
                    "glyphName": record["name"],
                    "unicodes": list(record["unicodes"]),
                    "message": "Target glyph has multiple Unicode assignments; their order is preserved.",
                }
            )

    occupied = set()
    owners = {}
    for record in records.values():
        for value in record["unicodes"]:
            occupied.add(value)
            owners.setdefault(value, []).append(record["name"])

    changes = _previous_map_changes(records, previous)
    for item in changes["changed"]:
        errors.append(
            {
                "code": "previous_mapping_changed",
                "glyphName": item["glyphName"],
                "previousUnicodes": item["previousUnicodes"],
                "currentUnicodes": item["currentUnicodes"],
                "message": "Current assignments differ from the supplied previous map.",
            }
        )
    for item in changes["removed"]:
        warnings.append(
            {
                "code": "previous_glyph_removed",
                "glyphName": item["glyphName"],
                "reservedUnicodes": item["previousUnicodes"],
                "message": "Removed glyph values remain reserved by the supplied previous map.",
            }
        )

    proposed = []
    proposed_names = set()
    claimed = set()

    candidates = [
        record
        for record in target_records
        if record["export"] and not record["unicodes"] and not record["invalidUnicodeCount"]
    ]

    if allocate_unencoded:
        for record in candidates:
            name = record["name"]
            previous_values = previous.get(name)
            if not previous_values:
                continue
            collisions = []
            for value in previous_values:
                other_owners = [owner for owner in owners.get(value, []) if owner != name]
                if other_owners or value in claimed:
                    collisions.append({"codepoint": value, "glyphNames": sorted(other_owners)})
            if collisions:
                errors.append(
                    {
                        "code": "previous_mapping_collision",
                        "glyphName": name,
                        "collisions": collisions,
                        "message": "Previous assignments cannot be restored without a collision.",
                    }
                )
                continue
            proposed.append(
                {
                    "glyphName": name,
                    "expectedUnicodes": [],
                    "unicodes": list(previous_values),
                    "source": "previous_map",
                }
            )
            proposed_names.add(name)
            claimed.update(previous_values)

        new_candidates = [record for record in candidates if record["name"] not in proposed_names]
        available_count = 0
        available_values = []
        for value in _iter_assignable_range(start, end, direction_value):
            if value in occupied or value in reserved or value in claimed:
                continue
            available_count += 1
            if len(available_values) < len(new_candidates):
                available_values.append(value)
        if available_count < len(new_candidates):
            errors.append(
                {
                    "code": "allocation_range_exhausted",
                    "needed": len(new_candidates),
                    "available": available_count,
                    "message": "The configured range has insufficient unused values.",
                }
            )
        else:
            for record, value in zip(new_candidates, available_values):
                proposed.append(
                    {
                        "glyphName": record["name"],
                        "expectedUnicodes": [],
                        "unicodes": [value],
                        "source": "allocated",
                    }
                )
                claimed.add(value)

        if not _range_is_private_use(start, end):
            warnings.append(
                {
                    "code": "semantic_validation_required",
                    "rangeStart": format_codepoint(start),
                    "rangeEnd": format_codepoint(end),
                    "message": "The allocation range is not wholly private-use; character semantics were not evaluated.",
                }
            )

    proposed.sort(key=lambda item: item["glyphName"])

    pua_glyphs = set()
    for record in records.values():
        if any(is_private_use(parse_codepoint(value)) for value in record["unicodes"]):
            pua_glyphs.add(record["name"])
    for item in proposed:
        if any(is_private_use(parse_codepoint(value)) for value in item["unicodes"]):
            pua_glyphs.add(item["glyphName"])
    if pua_glyphs:
        warnings.append(
            {
                "code": "private_agreement_required",
                "glyphCount": len(pua_glyphs),
                "glyphNames": sorted(pua_glyphs),
                "message": "Private-use assignments require an external agreement defining their meaning.",
            }
        )

    assignable_count = sum(1 for _value in _iter_assignable_range(start, end, "ascending"))

    def in_assignable_range(value):
        codepoint = parse_codepoint(value)
        return start <= codepoint <= end and not is_noncharacter(codepoint)

    occupied_in_range = {value for value in occupied if in_assignable_range(value)}
    reserved_in_range = {value for value in reserved if in_assignable_range(value)}
    unavailable_in_range = occupied_in_range.union(reserved_in_range)
    newly_allocated_in_range = {
        value
        for item in proposed
        if item.get("source") == "allocated"
        for value in item["unicodes"]
        if in_assignable_range(value)
    }

    all_records = list(records.values())
    target_valid_records = [record for record in target_records if not record["invalidUnicodeCount"]]
    current_map = {name: list(records[name]["unicodes"]) for name in sorted(records)}
    current_classifications = {
        name: [
            {
                "codepoint": value,
                "classification": classify_codepoint(value),
            }
            for value in records[name]["unicodes"]
        ]
        for name in sorted(records)
    }
    for item in proposed:
        item["classifications"] = [
            {
                "codepoint": value,
                "classification": classify_codepoint(value),
            }
            for value in item["unicodes"]
        ]

    return {
        "currentMap": current_map,
        "currentClassifications": current_classifications,
        "fontCounts": {
            "glyphCount": len(all_records),
            "exportingGlyphCount": sum(1 for record in all_records if record["export"]),
            "encodedGlyphCount": sum(1 for record in all_records if record["unicodes"]),
            "unencodedGlyphCount": sum(1 for record in all_records if not record["unicodes"]),
            "privateUseGlyphCount": sum(
                1
                for record in all_records
                if any(is_private_use(parse_codepoint(value)) for value in record["unicodes"])
            ),
            "standardUnicodeGlyphCount": sum(
                1
                for record in all_records
                if any(classify_codepoint(value) == "standard" for value in record["unicodes"])
            ),
            "noncharacterGlyphCount": sum(
                1
                for record in all_records
                if any(classify_codepoint(value) == "noncharacter" for value in record["unicodes"])
            ),
            "invalidUnicodeCount": sum(record["invalidUnicodeCount"] for record in all_records),
        },
        "targetCounts": {
            "requestedGlyphCount": len(names),
            "foundGlyphCount": len(target_records),
            "encodedGlyphCount": sum(1 for record in target_valid_records if record["unicodes"]),
            "unencodedExportingGlyphCount": sum(
                1 for record in target_valid_records if record["export"] and not record["unicodes"]
            ),
            "proposedAssignmentCount": len(proposed),
        },
        "range": {
            "start": format_codepoint(start),
            "end": format_codepoint(end),
            "direction": direction_value,
            "privateUseOnly": _range_is_private_use(start, end),
            "assignableCount": assignable_count,
            "occupiedCount": len(occupied_in_range),
            "reservedCount": len(reserved_in_range),
            "proposedCount": len(newly_allocated_in_range),
            "remainingCount": assignable_count
            - len(unavailable_in_range)
            - len(newly_allocated_in_range),
        },
        "errors": errors,
        "warnings": warnings,
        "proposedAssignments": proposed,
        "changes": changes,
    }


def prepare_assignment_changes(glyphs, assignments):
    """Validate explicit assignment changes against a complete font snapshot."""
    records, record_errors = _normalize_glyph_records(glyphs)
    errors = list(record_errors)
    warnings = []
    actions = []

    if not isinstance(assignments, list) or not assignments:
        return {
            "ok": False,
            "errors": [
                {
                    "code": "assignments_required",
                    "message": "assignments must be a non-empty list.",
                }
            ],
            "warnings": [],
            "actions": [],
        }

    seen_names = set()
    for index, raw in enumerate(assignments):
        if not isinstance(raw, dict):
            errors.append(
                {
                    "code": "invalid_assignment",
                    "assignmentIndex": index,
                    "message": "Each assignment must be an object.",
                }
            )
            continue
        name = str(raw.get("glyphName") or "").strip()
        if not name:
            errors.append(
                {
                    "code": "glyph_name_required",
                    "assignmentIndex": index,
                    "message": "Each assignment requires glyphName.",
                }
            )
            continue
        if name in seen_names:
            errors.append(
                {
                    "code": "duplicate_glyph_assignment",
                    "glyphName": name,
                    "message": "A glyph may appear only once in an assignment batch.",
                }
            )
            continue
        seen_names.add(name)

        if name not in records:
            errors.append(
                {
                    "code": "glyph_not_found",
                    "glyphName": name,
                    "message": "Glyph '{}' was not found.".format(name),
                }
            )
            continue
        if "expectedUnicodes" not in raw or "unicodes" not in raw:
            errors.append(
                {
                    "code": "assignment_state_required",
                    "glyphName": name,
                    "message": "Assignments require expectedUnicodes and unicodes.",
                }
            )
            continue

        expected, expected_errors = _normalize_values(
            raw.get("expectedUnicodes"),
            "assignments.{}.expectedUnicodes".format(name),
            reject_duplicates=True,
        )
        desired, desired_errors = _normalize_values(
            raw.get("unicodes"),
            "assignments.{}.unicodes".format(name),
            reject_duplicates=True,
        )
        for item in expected_errors + desired_errors:
            item["glyphName"] = name
        errors.extend(expected_errors)
        errors.extend(desired_errors)
        if expected_errors or desired_errors:
            continue

        current = list(records[name]["unicodes"])
        if current != expected:
            errors.append(
                {
                    "code": "stale_expected_state",
                    "glyphName": name,
                    "expectedUnicodes": expected,
                    "currentUnicodes": current,
                    "message": "Glyph assignments changed after review.",
                }
            )
            continue

        actions.append(
            {
                "glyphName": name,
                "before": current,
                "after": desired,
                "changed": current != desired,
            }
        )

        noncharacters = [value for value in desired if is_noncharacter(parse_codepoint(value))]
        if noncharacters:
            warnings.append(
                {
                    "code": "noncharacter_assignment",
                    "glyphName": name,
                    "unicodes": noncharacters,
                    "message": "Explicit assignment includes Unicode noncharacters.",
                }
            )

    final_map = {name: list(record["unicodes"]) for name, record in records.items()}
    for action in actions:
        final_map[action["glyphName"]] = list(action["after"])

    owners = {}
    for name, values in final_map.items():
        for value in values:
            owners.setdefault(value, []).append(name)
    for value, names in sorted(owners.items()):
        unique_names = sorted(set(names))
        if len(unique_names) > 1:
            errors.append(
                {
                    "code": "unicode_collision",
                    "codepoint": value,
                    "glyphNames": unique_names,
                    "message": "Resulting assignments would map one codepoint to multiple glyphs.",
                }
            )

    pua_names = sorted(
        action["glyphName"]
        for action in actions
        if any(is_private_use(parse_codepoint(value)) for value in action["after"])
    )
    if pua_names:
        warnings.append(
            {
                "code": "private_agreement_required",
                "glyphNames": pua_names,
                "message": "Private-use assignments require an external agreement defining their meaning.",
            }
        )

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "actions": actions,
    }


__all__ = [
    "BMP_PUA_END",
    "BMP_PUA_START",
    "SUPPLEMENTARY_PUA_A_END",
    "SUPPLEMENTARY_PUA_A_START",
    "SUPPLEMENTARY_PUA_B_END",
    "SUPPLEMENTARY_PUA_B_START",
    "classify_codepoint",
    "format_codepoint",
    "is_noncharacter",
    "is_private_use",
    "is_surrogate",
    "normalize_codepoint",
    "normalize_codepoints",
    "parse_codepoint",
    "prepare_assignment_changes",
    "review_assignments",
]
