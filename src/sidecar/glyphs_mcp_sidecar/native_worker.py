"""Native width job executed only by ``glyphs run --plugins ''``."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from glyphs_mcp_protocol import PATCH_VERSION, validate_patch, validate_worker_result
from .worker import WORKER_ERROR_PREFIX, WorkerError


def _load_font(path: Path) -> Any:
    from Foundation import NSURL  # type: ignore[import-not-found]
    from GlyphsApp import GSFont  # type: ignore[import-not-found]

    loaded = GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(str(path)), None)
    font = loaded[0] if isinstance(loaded, tuple) else loaded
    if font is None:
        raise RuntimeError("Glyphs could not load the saved source")
    # This font exists only in the external worker and is never saved. Native
    # parented component bounds otherwise use the document's display grid even
    # with layer rounding suppressed. Compute physical geometry without it.
    font.grid = 0
    return font


def _number(value: Any) -> float | int:
    result = float(value)
    return int(result) if result.is_integer() else result


def build_patch(payload: dict[str, Any]) -> dict[str, Any]:
    request = payload["request"]
    if request.get("kind") in ("spacing", "kerning_collision", "start_nodes", "slant", "outline_edit", "native_action", "dimensions_edit"):
        from .spacing_job import prepare as spacing_prepare
        from .kerning_job import prepare as kerning_prepare
        from .start_node_job import prepare as start_prepare
        from .slant_job import prepare as slant_prepare
        from .outline_job import prepare as outline_prepare
        from .native_action_job import prepare as native_action_prepare
        from .dimensions_job import prepare as dimensions_prepare
        prepare = {"spacing": spacing_prepare, "kerning_collision": kerning_prepare, "start_nodes": start_prepare, "slant": slant_prepare, "outline_edit": outline_prepare, "native_action": native_action_prepare, "dimensions_edit": dimensions_prepare}[request["kind"]]
        changes, report = prepare(_load_font(Path(payload["source"])), request)
        Path(payload["output"]).with_name("report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return validate_patch({"version": PATCH_VERSION, "jobId": payload["jobId"],
                              "documentId": payload["document"]["id"], "sourcePath": payload["document"]["path"],
                              "sourceHash": payload["sourceHash"], "generation": payload["document"]["generation"],
                              "changes": changes, "summary": ("Spacing suggestions for {} master layers".format(len(report["layers"]))
                              if request["kind"] == "spacing" else "Start-node correspondence for {} master layers".format(len(report["layers"]))
                              if request["kind"] == "start_nodes" else "Slant suggestions for {} master layers".format(len(report["layers"]))
                              if request["kind"] == "slant" else "Outline edits for {} layers".format(len(report["layers"]))
                              if request["kind"] == "outline_edit" else "Native {} action for {} targets".format(report["action"], report["targetCount"])
                              if request["kind"] == "native_action" else "Dimensions reference edits for {} fields".format(len(report["targets"]))
                              if request["kind"] == "dimensions_edit" else "Collision corrections for {} master pairs".format(len(report["pairs"])))})
    if request.get("kind") != "width_delta":
        raise ValueError("unsupported external job kind")
    delta = float(request["delta"])
    names = {str(value) for value in request.get("glyphs") or []}
    font = _load_font(Path(payload["source"]))
    glyphs = list(font.glyphs or [])
    missing = sorted(names - {str(glyph.name or "") for glyph in glyphs})
    if missing:
        raise ValueError("width_delta requested glyphs missing from saved source: "
                         + json.dumps(missing, ensure_ascii=False))
    changes = []
    for glyph in glyphs:
        glyph_name = str(glyph.name or "")
        if not glyph_name or names and glyph_name not in names:
            continue
        for layer in list(glyph.layers or []):
            layer_id = str(layer.layerId or layer.associatedMasterId or "")
            if not layer_id:
                continue
            before = _number(layer.width)
            after = _number(float(before) + delta)
            if after == before:
                continue
            changes.append(
                {
                    "kind": "set",
                    "glyph": glyph_name,
                    "layer": layer_id,
                    "field": "width",
                    "before": before,
                    "after": after,
                }
            )
    if not changes:
        raise ValueError("the job selected no writable layers")
    selected = "selected glyphs" if names else "all layers"
    return validate_patch(
        {
            "version": PATCH_VERSION,
            "jobId": payload["jobId"],
            "documentId": payload["document"]["id"],
            "sourcePath": payload["document"]["path"],
            "sourceHash": payload["sourceHash"],
            "generation": payload["document"]["generation"],
            "changes": changes,
            "summary": "Add {} units to {}".format(_number(delta), selected),
        }
    )


def build_result(payload: dict[str, Any]) -> dict[str, Any]:
    request = payload.get("request") or {}
    if request.get("kind") == "font_export":
        from .font_export_job import prepare as export_prepare

        manifest, report = export_prepare(
            _load_font(Path(payload["source"])), request, Path(payload["output"]).parent
        )
        Path(payload["output"]).with_name("report.json").write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return validate_worker_result({
            "version": PATCH_VERSION,
            "resultKind": "artifact",
            "jobId": payload["jobId"],
            "documentId": payload["document"]["id"],
            "sourcePath": payload["document"]["path"],
            "sourceHash": payload["sourceHash"],
            "generation": payload["document"]["generation"],
            "summary": "Exported and verified {}".format(report["instanceName"] or report["instanceId"]),
            "manifest": manifest,
            "report": report,
        })
    if request.get("kind") != "feature_compile":
        return build_patch(payload)
    from .feature_compile_job import prepare

    report = prepare(_load_font(Path(payload["source"])), request)
    Path(payload["output"]).with_name("report.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return validate_worker_result({
        "version": PATCH_VERSION,
        "resultKind": "diagnostic",
        "jobId": payload["jobId"],
        "documentId": payload["document"]["id"],
        "sourcePath": payload["document"]["path"],
        "sourceHash": payload["sourceHash"],
        "generation": payload["document"]["generation"],
        "summary": "OpenType compilation succeeded" if report["success"] else "OpenType compilation failed",
        "report": report,
    })


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv or sys.argv[1:])
    if not arguments:
        raise SystemExit("worker request path is required")
    request_path = Path(arguments[-1]).resolve()
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    try:
        result = build_result(payload)
    except WorkerError as error:
        # Expected target validation failures are user-facing evidence, not a
        # Python traceback. Unexpected failures retain the existing diagnostics.
        print(WORKER_ERROR_PREFIX + json.dumps(str(error), ensure_ascii=False), file=sys.stderr)
        return 1
    output = Path(payload["output"]).resolve()
    output.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
