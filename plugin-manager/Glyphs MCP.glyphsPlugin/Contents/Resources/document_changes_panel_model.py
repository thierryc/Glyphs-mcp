# encoding: utf-8

"""Pure presentation helpers for the native Glyphs MCP Changes panel."""

from __future__ import annotations

import json


def _translate(translator, key, fallback, **values):
    if translator is None:
        try:
            return fallback.format(**values)
        except Exception:
            return fallback
    translated = translator(key, **values)
    return fallback.format(**values) if translated == key else translated


def panel_rows(snapshot, translator=None):
    rows = []
    for event in list((snapshot or {}).get("entries") or []):
        target = event.get("target") if isinstance(event.get("target"), dict) else {}
        glyphs = glyph_names_for_event(event)
        target_label = ", ".join(glyphs[:3])
        if len(glyphs) > 3:
            target_label += " +{}".format(len(glyphs) - 3)
        if not target_label:
            target_label = target.get("masterName") or target.get("masterId") or _translate(
                translator, "changes.document", "Document"
            )
        timestamp = str(event.get("timestamp") or "")
        outcome = str(event.get("outcome") or "unknown")
        rows.append(
            {
                "time": timestamp[11:19] if len(timestamp) >= 19 else timestamp,
                "outcome": _translate(
                    translator,
                    "changes.outcome.{}".format(outcome),
                    outcome.replace("_", " ").title(),
                ),
                "action": str(
                    event.get("title")
                    or event.get("tool")
                    or _translate(translator, "changes.mutation", "MCP mutation")
                ),
                "target": str(target_label),
                "event": event,
            }
        )
    return rows


def glyph_names_for_event(event):
    target = (event or {}).get("target")
    if not isinstance(target, dict):
        return []
    values = []
    if target.get("glyphName"):
        values.append(str(target["glyphName"]))
    for key in ("glyphNames", "sourceGlyph", "targetGlyph"):
        value = target.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value if item)
        elif value:
            values.append(str(value))
    for key in ("left", "right"):
        value = target.get(key)
        if value and not str(value).startswith("@"):
            values.append(str(value))
    result = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result[:64]


def counts_text(snapshot, translator=None):
    counts = (snapshot or {}).get("counts") or {}
    return _translate(
        translator,
        "changes.counts",
        "Changed {changed}   Succeeded {succeeded}   Failed {failed}   Uncertain {uncertain}   Saves {saved}",
        changed=counts.get("changed", 0),
        succeeded=counts.get("succeeded", 0),
        failed=counts.get("failed", 0),
        uncertain=counts.get("uncertain", 0),
        saved=counts.get("saved", 0),
    )


def header_text(snapshot, translator=None):
    if (snapshot or {}).get("status") != "active":
        return _translate(
            translator,
            "changes.empty",
            "No document is being tracked. Tracking starts with the first MCP mutation.",
        )
    target = (snapshot or {}).get("target") or {}
    family_name = target.get("familyName") or _translate(
        translator, "changes.untitled", "Untitled font"
    )
    file_state = target.get("filePath") or _translate(
        translator, "changes.unsaved", "Unsaved document"
    )
    return "{} — {}".format(family_name, file_state)


def retention_text(snapshot, translator=None):
    text = _translate(
        translator,
        "changes.retention",
        "Current Glyphs run · up to 256 recent events; aggregate counts are retained",
    )
    started_at = (snapshot or {}).get("startedAt")
    if started_at:
        text = "{}   {}".format(
            _translate(
                translator,
                "changes.session_started",
                "Started {time}",
                time=str(started_at).replace("T", " ")[:19],
            ),
            text,
        )
    omitted = int((snapshot or {}).get("omittedEntryCount") or 0)
    if omitted:
        text = "{}   {}".format(
            text,
            _translate(
                translator,
                "changes.omitted",
                "{count} earlier event(s) omitted",
                count=omitted,
            ),
        )
    return text


def detail_text(event, translator=None, overview_warnings=None):
    if not event:
        lines = [
            _translate(
                translator,
                "changes.select_event",
                "Select an activity row to inspect its bounded details.",
            ),
        ]
    else:
        lines = [
            "{} — {}".format(
                event.get("title")
                or event.get("tool")
                or _translate(translator, "changes.mutation", "MCP mutation"),
                _translate(
                    translator,
                    "changes.outcome.{}".format(event.get("outcome") or "unknown"),
                    str(event.get("outcome") or "unknown").replace("_", " ").title(),
                ),
            ),
            str(event.get("summary") or "No summary returned."),
        ]
        target = event.get("target")
        if isinstance(target, dict) and target:
            lines.append(
                _translate(
                    translator,
                    "changes.target_detail",
                    "Target: {target}",
                    target=json.dumps(target, sort_keys=True, ensure_ascii=False, default=str),
                )
            )
    warnings = list((event or {}).get("warnings") or []) + list(overview_warnings or [])
    seen_warnings = set()
    for warning in warnings:
        warning = str(warning)
        if warning in seen_warnings:
            continue
        seen_warnings.add(warning)
        lines.append(
            _translate(
                translator,
                "changes.warning_detail",
                "Warning: {warning}",
                warning=warning,
            )
        )
    if (event or {}).get("opaque"):
        lines.append(
            _translate(
                translator,
                "changes.opaque_detail",
                "This generic code operation is opaque; its document effects were not inspected.",
            )
        )
    return "\n".join(lines)


__all__ = [
    "counts_text",
    "detail_text",
    "glyph_names_for_event",
    "header_text",
    "panel_rows",
    "retention_text",
]
