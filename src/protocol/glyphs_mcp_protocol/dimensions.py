"""Closed Dimensions palette contract and bounded metadata access, without UI code."""
from collections.abc import Mapping
from decimal import Decimal
import math
import re

from .models import ProtocolError, canonical_json

STORAGE_KEY = "GSDimensionPlugin.Dimensions"
READ_CAPABILITY = "master.dimensions.read.v1"
WRITE_CAPABILITY = "master.dimensions.edit.v1"
MAX_CHANGES = 100
MAX_FIELDS = 256
MAX_MASTERS = 4096

# Identifiers read from Glyphs 4.1 (4107)'s actual palette outlets, not inferred
# from outlet names (notably kanada*, Burmese*, and shared Cyrillic fields).
CATALOG = {}


def _fields(script, rows):
    for key, label in rows:
        CATALOG[key] = {"key": key, "label": label, "script": script}


_fields("latin/cyrillic", [("HV", "H / Д vertical stem"), ("HH", "H / Д horizontal stroke"),
    ("OV", "O vertical stroke"), ("OH", "O horizontal stroke"),
    ("nV", "n / д vertical stem"), ("oV", "o vertical stroke"), ("oH", "o horizontal stroke")])
_fields("latin", [("nd", "n shoulder"), ("tH", "t crossbar"),
    ("VThin", "V thin diagonal"), ("VThick", "V thick diagonal"),
    ("vThin", "v thin diagonal"), ("vThick", "v thick diagonal")])
_fields("cyrillic", [("cyDeVthin", "Д thin stroke"), ("cyHook", "Uppercase hook"),
    ("cydeVthin", "д thin stroke"), ("cydeH", "д horizontal stroke"), ("cyhook", "Lowercase hook")])
_fields("arabic", [("arAlef", "Alef stem"), ("arBar", "Horizontal stroke"),
    ("arRoundThin", "Thin round stroke"), ("arRoundThick", "Thick round stroke")])
for _script in ("thai", "lao"):
    _fields(_script, [(_script + key, label) for key, label in (
        ("HBall", "Loop horizontal stroke"), ("VBall", "Loop vertical stroke"),
        ("HStem", "Horizontal stem"), ("VStem", "Vertical stem"), ("HRound", "Round horizontal stroke"))])
_fields("myanmar", [("Burmese" + key, label) for key, label in (
    ("Thin", "Thin stroke"), ("HRound", "Round horizontal stroke"),
    ("VRound", "Round vertical stroke"), ("VStem", "Vertical stem"), ("HStem", "Horizontal stem"))])
for _script, _prefix, _count in (("han", "han", 8), ("kannada", "kanada", 8), ("khmer", "khmer", 7)):
    _fields(_script, [(_prefix + str(i), f"{_script.title()} palette reference {i}") for i in range(1, _count + 1)])


def fail(message, code="invalid_request"):
    raise ProtocolError(code, message)


def number(value, *, stored=False):
    if stored and isinstance(value, str) and len(value) <= 80 and re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value):
        value = int(value) if re.fullmatch(r"[+-]?\d+", value) else float(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail("Dimensions values must be finite numbers")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        fail("Dimensions values must be finite numbers")
    return value


def same_number(left, right):
    number(left, stored=True); number(right)
    return Decimal(str(left)) == Decimal(str(right))


def target(value):
    for name in ("master", "key"):
        if not isinstance(value.get(name), str) or not 1 <= len(value[name]) <= 255:
            fail("Dimensions targets require exact master and field keys")
    if value["key"] not in CATALOG:
        fail("Unverified Dimensions field: " + value["key"], "unsupported_dimension")


def validate_options(value):
    if not isinstance(value, Mapping) or set(value) != {"changes"}:
        fail("dimensions_edit requires options.changes only")
    rows = value["changes"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CHANGES:
        fail("dimensions_edit requires 1-100 field changes")
    seen, result = set(), []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"master", "key", "value"}:
            fail("Each Dimensions request requires master, key and value")
        target(row)
        identity = (row["master"], row["key"])
        if identity in seen:
            fail("Duplicate Dimensions target")
        seen.add(identity)
        result.append({**row, "value": None if row["value"] is None else number(row["value"])})
    return {"changes": result}


def state(value):
    if not isinstance(value, Mapping) or set(value) != {"present", "value"} or type(value["present"]) is not bool:
        fail("Dimensions state requires presence and exact stored value")
    if value["present"]:
        number(value["value"], stored=True)
    elif value["value"] is not None:
        fail("An absent Dimensions value must be null")
    return dict(value)


def validate_change(value):
    if set(value) != {"kind", "master", "key", "before", "after", "containersBefore"}:
        fail("Dimensions change fields are incomplete or unexpected")
    target(value)
    before, after = state(value["before"]), state(value["after"])
    containers = value["containersBefore"]
    if (not isinstance(containers, Mapping) or set(containers) != {"root", "master"}
            or any(type(v) is not bool for v in containers.values())
            or containers["master"] and not containers["root"]
            or before["present"] and not containers["master"]):
        fail("Invalid Dimensions container presence")
    if before == after:
        fail("Dimensions change has no effect")
    return {**value, "before": before, "after": after, "containersBefore": dict(containers)}


def approval_entries(changes):
    return [{k: row[k] for k in ("master", "key", "before", "after")}
            for row in changes if row.get("kind") == "dimension" and row["before"]["present"]]


def validate_approval(changes, approved):
    required = approval_entries(changes)
    approved = [] if approved is None else approved
    if not isinstance(approved, list) or len(approved) > MAX_CHANGES:
        fail("approved_overwrites must contain at most 100 exact entries")
    for row in approved:
        if not isinstance(row, Mapping) or set(row) != {"master", "key", "before", "after"}:
            fail("Overwrite approvals require exact master, key, before and after")
        target(row); state(row["before"]); state(row["after"])
    if sorted(map(canonical_json, required)) != sorted(map(canonical_json, approved)):
        fail("Show the exact existing and proposed Dimensions values and obtain conversational approval before overwriting or clearing them", "overwrite_approval_required")
    return approved


def containers(root, master):
    if root is None:
        return {}, {}, {"root": False, "master": False}
    if not isinstance(root, Mapping) or len(root) > MAX_MASTERS:
        fail("Malformed or oversized Dimensions dictionary", "invalid_dimensions")
    table = root.get(master, {})
    if not isinstance(table, Mapping) or len(table) > MAX_FIELDS or any(not isinstance(k, str) or len(k) > 255 for k in table):
        fail("Malformed or oversized master Dimensions dictionary", "invalid_dimensions")
    return root, table, {"root": True, "master": master in root}


def read_state(root, master, key):
    _, table, _ = containers(root, master)
    result = {"present": key in table, "value": table.get(key)}
    try:
        return state(result)
    except ProtocolError as exc:
        fail("Stored Dimensions value is malformed; correct it in Glyphs before editing: " + key, "invalid_dimensions")


def replace(root, master, key, wanted, original):
    """Copy only the namespace and selected master; retain unknown native values."""
    root, table, _ = containers(root, master)
    root, table = dict(root), dict(table)
    if wanted["present"]:
        table[key] = wanted["value"]
    else:
        table.pop(key, None)
    if table or original["master"]:
        root[master] = table
    else:
        root.pop(master, None)
    return root if root or original["root"] else None


def read_rows(root, master, *, editable):
    _, table, _ = containers(root, master)
    keys = sorted(set(CATALOG) | set(table))
    rows = []
    for key in keys:
        row = {**CATALOG.get(key, {"key": key, "label": None, "script": None}),
               "present": key in table, "value": None, "storedValue": None,
               "editable": bool(editable and key in CATALOG), "valid": True}
        if key in table:
            try:
                row.update(value=number(table[key], stored=True), storedValue=table[key])
            except ProtocolError:
                row.update(valid=False, editable=False, storedType=type(table[key]).__name__)
                if isinstance(table[key], str): row["storedValue"] = table[key][:80]
        rows.append(row)
    return {"items": rows, "total": len(rows), "returned": len(rows), "complete": True}
