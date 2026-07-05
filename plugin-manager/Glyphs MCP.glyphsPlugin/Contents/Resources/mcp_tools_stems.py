# encoding: utf-8

from __future__ import division, print_function, unicode_literals

from GlyphsApp import Glyphs, GSMetric  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import _coerce_numeric, _font_resolution_error, _resolve_font_by_index, _safe_json

import stem_metrics_helpers


def _get_font(font_index):
    font, _fonts = _resolve_font_by_index(Glyphs, font_index)
    return font


def _master_by_id(font, master_id):
    if not master_id:
        return None
    for master in list(getattr(font, "masters", []) or []):
        if str(getattr(master, "id", "")) == str(master_id):
            return master
    return None


def _stem_entries_by_orientation(entries, orientation):
    return [entry for entry in entries if entry.get("orientation") == orientation]


def _usable_stems(entries, orientation):
    return [entry for entry in _stem_entries_by_orientation(entries, orientation) if entry.get("ok")]


def _review_master_stem_metrics_impl(
    font_index=0,
    master_ids=None,
    reference_glyphs=None,
    include_measurements=True,
    samples=9,
    band=0.2,
    min_width=5.0,
    max_width=None,
    include_components=True,
):
    try:
        font = _get_font(font_index)
        if not font:
            _font, fonts = _resolve_font_by_index(Glyphs, font_index)
            return _font_resolution_error(font_index, fonts, ok_key="ok")

        masters = list(getattr(font, "masters", []) or [])
        if not masters:
            return {"ok": False, "error": "Font has no masters", "fontIndex": font_index}

        requested_ids = [str(mid) for mid in list(master_ids or []) if mid]
        if requested_ids:
            target_masters = []
            missing = []
            for mid in requested_ids:
                master = _master_by_id(font, mid)
                if master:
                    target_masters.append(master)
                else:
                    missing.append(mid)
            if missing:
                return {"ok": False, "error": "Master ID not found", "missingMasterIds": missing}
        else:
            target_masters = masters

        definitions = stem_metrics_helpers.font_stem_definitions(font)
        master_reports = []
        ready_count = 0

        for master in target_masters:
            entries = stem_metrics_helpers.master_stem_report(font, master)
            vertical_ok = _usable_stems(entries, "vertical")
            horizontal_ok = _usable_stems(entries, "horizontal")
            missing_orientations = []
            if not vertical_ok:
                missing_orientations.append("vertical")
            if not horizontal_ok:
                missing_orientations.append("horizontal")

            estimates = {}
            if include_measurements:
                estimates["vertical"] = stem_metrics_helpers.estimate_master_stem(
                    font=font,
                    master=master,
                    orientation="vertical",
                    reference_glyphs=reference_glyphs,
                    samples=samples,
                    band=band,
                    min_width=min_width,
                    max_width=max_width,
                    include_components=include_components,
                )
                estimates["horizontal"] = stem_metrics_helpers.estimate_master_stem(
                    font=font,
                    master=master,
                    orientation="horizontal",
                    reference_glyphs=reference_glyphs,
                    samples=samples,
                    band=band,
                    min_width=min_width,
                    max_width=max_width,
                    include_components=include_components,
                )

            ready = len(missing_orientations) == 0
            if ready:
                ready_count += 1

            master_reports.append(
                {
                    "masterId": getattr(master, "id", None),
                    "masterName": getattr(master, "name", None),
                    "readyForCursivy": ready,
                    "missingOrientations": missing_orientations,
                    "stems": entries,
                    "usable": {
                        "vertical": vertical_ok,
                        "horizontal": horizontal_ok,
                    },
                    "measurements": estimates,
                }
            )

        warnings = []
        if not definitions:
            warnings.append("font_has_no_stem_definitions")

        return {
            "ok": True,
            "fontIndex": font_index,
            "familyName": getattr(font, "familyName", None),
            "readyForCursivy": ready_count == len(master_reports),
            "summary": {
                "masterCount": len(master_reports),
                "readyCount": ready_count,
                "definitionCount": len(definitions),
            },
            "definitions": [
                {
                    "name": item.get("name"),
                    "index": item.get("index"),
                    "orientation": item.get("orientation"),
                    "horizontal": item.get("horizontal"),
                }
                for item in definitions
            ],
            "masters": master_reports,
            "warnings": warnings,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _normalize_stem_requests(stems, vertical_stem, horizontal_stem, vertical_name, horizontal_name):
    requests = []
    for item in list(stems or []):
        if not isinstance(item, dict):
            continue
        requests.append(
            {
                "name": str(item.get("name") or "").strip(),
                "orientation": str(item.get("orientation") or "").strip().lower(),
                "value": item.get("value"),
            }
        )

    if vertical_stem is not None:
        requests.append({"name": vertical_name or "Vertical", "orientation": "vertical", "value": vertical_stem})
    if horizontal_stem is not None:
        requests.append({"name": horizontal_name or "Horizontal", "orientation": "horizontal", "value": horizontal_stem})
    return requests


def _find_stem_definition(font, name, orientation):
    wanted_horizontal = str(orientation or "").lower().startswith("h")
    for definition in stem_metrics_helpers.font_stem_definitions(font):
        if str(definition.get("name")) == str(name) and bool(definition.get("horizontal")) == wanted_horizontal:
            return definition
    return None


def _append_stem_definition(font, name, orientation):
    stem = GSMetric()
    stem.name = str(name)
    stem.horizontal = str(orientation or "").lower().startswith("h")
    font.stems.append(stem)
    definitions = stem_metrics_helpers.font_stem_definitions(font)
    for definition in definitions:
        if definition.get("stem") is stem:
            return definition
    return _find_stem_definition(font, name, orientation)


def _set_master_stem_value(master, name, value):
    stems = getattr(master, "stems", None)
    if stems is None:
        return False
    try:
        stems[str(name)] = float(value)
        return True
    except Exception:
        pass
    try:
        setattr(master, "stems", stems)
        stems[str(name)] = float(value)
        return True
    except Exception:
        return False


def _set_master_stem_metrics_impl(
    font_index=0,
    master_id=None,
    stems=None,
    vertical_stem=None,
    horizontal_stem=None,
    vertical_name="Vertical",
    horizontal_name="Horizontal",
    dry_run=False,
    confirm=False,
):
    try:
        font = _get_font(font_index)
        if not font:
            _font, fonts = _resolve_font_by_index(Glyphs, font_index)
            return _font_resolution_error(font_index, fonts, ok_key="ok")
        master = _master_by_id(font, master_id)
        if not master:
            return {"ok": False, "error": "Master ID not found", "masterId": master_id}
        if not dry_run and not confirm:
            return {"ok": False, "error": "Use dry_run=true first or confirm=true to mutate"}

        requests = _normalize_stem_requests(stems, vertical_stem, horizontal_stem, vertical_name, horizontal_name)
        if not requests:
            return {"ok": False, "error": "No stem values provided"}

        actions = []
        errors = []
        for request in requests:
            name = str(request.get("name") or "").strip()
            orientation = str(request.get("orientation") or "").strip().lower()
            value = _coerce_numeric(request.get("value"))
            if not name:
                errors.append({"request": request, "error": "Stem name is required"})
                continue
            if orientation not in ("vertical", "horizontal"):
                errors.append({"request": request, "error": "orientation must be vertical or horizontal"})
                continue
            if value is None or float(value) <= 0.0:
                errors.append({"request": request, "error": "Stem value must be a positive number"})
                continue

            definition = _find_stem_definition(font, name, orientation)
            exists = definition is not None
            current_value = stem_metrics_helpers.master_stem_value(master, definition) if definition else None
            action = {
                "name": name,
                "orientation": orientation,
                "value": float(value),
                "definitionExists": exists,
                "currentValue": current_value,
                "action": "update" if exists else "create",
            }
            actions.append(action)

        if errors:
            return {"ok": False, "errors": errors, "actions": actions}

        if dry_run:
            return {
                "ok": True,
                "dryRun": True,
                "fontIndex": font_index,
                "masterId": getattr(master, "id", master_id),
                "actions": actions,
                "summary": {"actionCount": len(actions), "createdCount": len([a for a in actions if a["action"] == "create"])},
            }

        applied = []
        for action in actions:
            definition = _find_stem_definition(font, action["name"], action["orientation"])
            if definition is None:
                definition = _append_stem_definition(font, action["name"], action["orientation"])
            if definition is None:
                return {"ok": False, "error": "Failed to create stem definition", "action": action}
            if not _set_master_stem_value(master, action["name"], action["value"]):
                return {"ok": False, "error": "Failed to set master stem value", "action": action}
            action["definitionExistsAfter"] = True
            applied.append(action)

        return {
            "ok": True,
            "dryRun": False,
            "fontIndex": font_index,
            "masterId": getattr(master, "id", master_id),
            "actions": applied,
            "summary": {"appliedCount": len(applied)},
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
async def review_master_stem_metrics(
    font_index: int = 0,
    master_ids: list = None,
    reference_glyphs: list = None,
    include_measurements: bool = True,
    samples: int = 9,
    band: float = 0.2,
    min_width: float = 5.0,
    max_width: float = None,
    include_components: bool = True,
) -> str:
    """Review master stem metrics required by Glyphs Cursivy and related filters."""
    return _safe_json(
        _review_master_stem_metrics_impl(
            font_index=font_index,
            master_ids=master_ids,
            reference_glyphs=reference_glyphs,
            include_measurements=include_measurements,
            samples=samples,
            band=band,
            min_width=min_width,
            max_width=max_width,
            include_components=include_components,
        )
    )


@mcp.tool()
async def set_master_stem_metrics(
    font_index: int = 0,
    master_id: str = None,
    stems: list = None,
    vertical_stem: float = None,
    horizontal_stem: float = None,
    vertical_name: str = "Vertical",
    horizontal_name: str = "Horizontal",
    dry_run: bool = False,
    confirm: bool = False,
) -> str:
    """Create or update master stem metrics with dry-run and confirm gates."""
    return _safe_json(
        _set_master_stem_metrics_impl(
            font_index=font_index,
            master_id=master_id,
            stems=stems,
            vertical_stem=vertical_stem,
            horizontal_stem=horizontal_stem,
            vertical_name=vertical_name,
            horizontal_name=horizontal_name,
            dry_run=dry_run,
            confirm=confirm,
        )
    )
