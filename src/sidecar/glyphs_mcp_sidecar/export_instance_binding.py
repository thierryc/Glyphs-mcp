"""Source-bound live-instance selection for a saved, read-only export worker."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from .source import source_hash
from .worker import WorkerError

FIELDS = ("id", "name", "type", "exports", "outlineFormat", "axisValues")
MAX_BINDING_BYTES = 4 * 1024 * 1024


def _record(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(FIELDS):
        raise WorkerError("export instance evidence is incomplete")
    identity, name, axes = value["id"], value["name"], value["axisValues"]
    if (not isinstance(identity, str) or not identity or len(identity) > 1024
            or name is not None and (not isinstance(name, str) or len(name) > 4096)
            or value["type"] not in ("static", "variable")
            or value["exports"] is not None and type(value["exports"]) is not bool
            or value["outlineFormat"] not in (None, "otf", "ttf")
            or not isinstance(axes, list) or len(axes) > 32
            or any(type(n) not in (int, float) or not math.isfinite(n) for n in axes)):
        raise WorkerError("export instance evidence is invalid")
    return {**dict(value), "axisValues": [float(n) for n in axes]}


def _same_document(service: Any, document: Mapping[str, Any], fingerprint: str) -> None:
    current = service._document(document["id"])
    if any(current.get(k) != document.get(k) for k in ("id", "path", "generation")) or current.get("dirty") is not False:
        raise WorkerError("document changed while binding the export instance")
    if source_hash(Path(document["path"])) != fingerprint:
        raise WorkerError("saved source changed while binding the export instance")


def capture(service: Any, document: Mapping[str, Any], identity: str, fingerprint: str) -> dict[str, Any]:
    """Resolve exact live ID once; never select a name or mutate native instances."""
    _same_document(service, document, fingerprint)
    cursor = None
    seen_cursors = set()
    records = []
    expected_total = None
    while True:
        selector = {"kind": "instances", "limit": 100}
        if cursor:
            selector["cursor"] = cursor
        response = service.bridge.read_entities(document["id"], [selector], ["items"])
        if not isinstance(response, list) or len(response) != 1:
            raise WorkerError("export instance page is unavailable")
        page = response[0].get("values", {})
        items, total = page.get("items"), page.get("total")
        if (not isinstance(items, list) or not 0 <= len(items) <= 100
                or type(total) is not int or total < 0
                or expected_total is not None and total != expected_total):
            raise WorkerError("export instance collection changed")
        expected_total = total
        ids = [item.get("id") for item in items if isinstance(item, Mapping)]
        if len(ids) != len(items) or any(not isinstance(n, str) or not n for n in ids):
            raise WorkerError("export instance page has no exact identities")
        if ids:
            entities = [{"kind": "instance", "id": n} for n in ids]
            exact = service.bridge.read_entities(document["id"], entities, list(FIELDS))
            if not isinstance(exact, list) or len(exact) != len(ids):
                raise WorkerError("export instance details are incomplete")
            for summary, entity, detail in zip(items, entities, exact):
                if detail.get("entity") != entity:
                    raise WorkerError("export instance details identify another target")
                record = _record(detail.get("values"))
                if any(record[k] != summary.get(k) for k in FIELDS if k != "axisValues"):
                    raise WorkerError("export instance changed during discovery")
                records.append(record)
        if len(json.dumps(records, ensure_ascii=False).encode("utf-8")) > MAX_BINDING_BYTES:
            raise WorkerError("export instance binding exceeds 4 MiB")
        if page.get("complete") is True:
            if page.get("nextCursor") is not None or len(records) != total:
                raise WorkerError("export instance page ended before the collection was complete")
            break
        cursor = page.get("nextCursor")
        if not ids or not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
            raise WorkerError("export instance pagination did not advance")
        seen_cursors.add(cursor)
    identities = [r["id"] for r in records]
    if len(set(identities)) != len(identities) or identities.count(identity) != 1:
        raise WorkerError("the exact live export instance is unavailable or ambiguous")
    index = identities.index(identity)
    if records[index]["exports"] is not True:
        raise WorkerError("the exact Glyphs instance is not enabled for export")
    _same_document(service, document, fingerprint)
    return {"version": 1, "sourceHash": fingerprint, "instanceId": identity,
            "index": index, "instances": records}


def _descriptor(record: Mapping[str, Any]) -> dict[str, Any]:
    return {k: record[k] for k in FIELDS if k != "id"}


def resolve(saved: list[dict[str, Any]], binding: Any, identity: str, fingerprint: str) -> tuple[int, dict[str, Any]]:
    """Validate the immutable slot, complete order and axes before remapping IDs."""
    if (not isinstance(binding, Mapping)
            or set(binding) != {"version", "sourceHash", "instanceId", "index", "instances"}
            or type(binding["version"]) is not int or binding["version"] != 1
            or binding["sourceHash"] != fingerprint or binding["instanceId"] != identity
            or type(binding["index"]) is not int or binding["index"] < 0
            or not isinstance(binding["instances"], list)):
        raise WorkerError("export instance binding does not match this saved source and request")
    live = [_record(r) for r in binding["instances"]]
    saved = [_record(r) for r in saved]
    index = binding["index"]
    if (len(live) != len(saved) or index >= len(saved)
            or live[index]["id"] != identity
            or len({r["id"] for r in live}) != len(live)
            or len({r["id"] for r in saved}) != len(saved)
            or any(_descriptor(a) != _descriptor(b) for a, b in zip(live, saved))):
        raise WorkerError("saved export instance collection differs from the bound live collection")
    exact = [i for i, r in enumerate(saved) if r["id"] == identity]
    if exact and exact != [index]:
        raise WorkerError("export instance ID identifies a different saved instance")
    if not exact and sum(_descriptor(r) == _descriptor(live[index]) for r in live) != 1:
        raise WorkerError("regenerated export instance identity is ambiguous")
    if saved[index]["exports"] is not True:
        raise WorkerError("the exact Glyphs instance is not enabled for export")
    return index, {"method": "exact-id" if exact else "source-bound-slot",
                   "requestedId": identity, "savedId": saved[index]["id"], "index": index}


def native_records(font: Any) -> list[dict[str, Any]]:
    def value(owner, key, default=None):
        item = getattr(owner, key, default)
        return item() if callable(item) else item
    rows = []
    for instance in list(value(font, "instances", []) or []):
        kind = value(instance, "type")
        kind = "variable" if kind in (1, "variable", "variableTT", "variableCFF") else "static" if kind in (0, "single", "static") else None
        outline = value(instance, "outlineFormat")
        outline = "otf" if outline in (0, "CFF", "OTF", "otf", "variableCFF") else "ttf" if outline in (1, "TT", "TTF", "ttf", "variableTT") else None
        enabled = value(instance, "exports", value(instance, "active"))
        enabled = bool(enabled) if type(enabled) in (bool, int) and enabled in (0, 1) else None
        rows.append(_record({"id": value(instance, "id"), "name": value(instance, "name"),
                             "type": kind, "exports": enabled, "outlineFormat": outline,
                             "axisValues": list(value(instance, "axes", []) or [])}))
    return rows
