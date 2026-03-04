# encoding: utf-8

from __future__ import division, print_function, unicode_literals

from GlyphsApp import Glyphs  # type: ignore[import-not-found]

from mcp_runtime import mcp
from mcp_tool_helpers import _safe_json

import smoothness_engine


@mcp.tool()
async def review_collinear_handles(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    path_index: int = None,
    node_indices: list = None,
    threshold_deg: float = 3.0,
    min_handle_len: float = 5.0,
    include_already_smooth: bool = False,
) -> str:
    """Review a single path for curve nodes that should be smooth based on handle collinearity.

    This is a targeted helper: you must specify glyph + master + path_index.
    It does not mutate anything.
    """
    try:
        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts)),
                }
            )

        if not glyph_name:
            return _safe_json({"ok": False, "error": "glyph_name is required"})
        if not master_id:
            return _safe_json({"ok": False, "error": "master_id is required"})
        if path_index is None:
            return _safe_json({"ok": False, "error": "path_index is required"})

        font = Glyphs.fonts[font_index]
        glyph = font.glyphs[glyph_name]
        if not glyph:
            return _safe_json({"ok": False, "error": "Glyph '{}' not found".format(glyph_name)})

        layer = glyph.layers[str(master_id)]
        if not layer:
            return _safe_json({"ok": False, "error": "Master ID '{}' not found".format(master_id)})

        paths = list(getattr(layer, "paths", []) or [])
        if int(path_index) < 0 or int(path_index) >= len(paths):
            return _safe_json(
                {
                    "ok": False,
                    "error": "path_index {} out of range. Available paths: {}".format(path_index, len(paths)),
                }
            )

        path = paths[int(path_index)]
        nodes = list(getattr(path, "nodes", []) or [])
        closed = bool(getattr(path, "closed", True))

        indices = None
        if node_indices is not None:
            if not isinstance(node_indices, list):
                return _safe_json({"ok": False, "error": "node_indices must be a list of integers"})
            indices = node_indices

        candidates = smoothness_engine.find_collinear_handle_nodes(
            nodes,
            closed=closed,
            threshold_deg=float(threshold_deg),
            min_handle_len=float(min_handle_len),
            node_indices=indices,
            include_already_smooth=bool(include_already_smooth),
            allowed_node_types=("curve",),
        )

        analyzed_nodes = len(indices) if indices is not None else len(nodes)
        return _safe_json(
            {
                "ok": True,
                "target": {
                    "fontIndex": int(font_index),
                    "glyphName": glyph_name,
                    "masterId": str(master_id),
                    "pathIndex": int(path_index),
                },
                "params": {"thresholdDeg": float(threshold_deg), "minHandleLen": float(min_handle_len)},
                "candidates": candidates,
                "summary": {"analyzedNodes": int(analyzed_nodes), "candidatesCount": int(len(candidates))},
            }
        )
    except Exception as e:
        return _safe_json({"ok": False, "error": str(e)})


@mcp.tool()
async def apply_collinear_handles_smooth(
    font_index: int = 0,
    glyph_name: str = None,
    master_id: str = None,
    path_index: int = None,
    node_indices: list = None,
    threshold_deg: float = 3.0,
    min_handle_len: float = 5.0,
    confirm: bool = False,
    dry_run: bool = False,
) -> str:
    """Set smooth=True for curve nodes in a single path when handles are nearly collinear.

    Safety:
    - Refuses to mutate unless confirm=true.
    - Use dry_run=true to preview.
    """
    try:
        if not confirm and not dry_run:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Refusing to apply smooth flags without confirm=true.",
                    "hint": "Run apply_collinear_handles_smooth(..., dry_run=true) to preview or set confirm=true to apply.",
                }
            )

        if font_index >= len(Glyphs.fonts) or font_index < 0:
            return _safe_json(
                {
                    "ok": False,
                    "error": "Font index {} out of range. Available fonts: {}".format(font_index, len(Glyphs.fonts)),
                }
            )

        if not glyph_name:
            return _safe_json({"ok": False, "error": "glyph_name is required"})
        if not master_id:
            return _safe_json({"ok": False, "error": "master_id is required"})
        if path_index is None:
            return _safe_json({"ok": False, "error": "path_index is required"})

        font = Glyphs.fonts[font_index]
        glyph = font.glyphs[glyph_name]
        if not glyph:
            return _safe_json({"ok": False, "error": "Glyph '{}' not found".format(glyph_name)})

        layer = glyph.layers[str(master_id)]
        if not layer:
            return _safe_json({"ok": False, "error": "Master ID '{}' not found".format(master_id)})

        paths = list(getattr(layer, "paths", []) or [])
        if int(path_index) < 0 or int(path_index) >= len(paths):
            return _safe_json(
                {
                    "ok": False,
                    "error": "path_index {} out of range. Available paths: {}".format(path_index, len(paths)),
                }
            )

        path = paths[int(path_index)]
        nodes = list(getattr(path, "nodes", []) or [])
        closed = bool(getattr(path, "closed", True))

        indices = list(range(len(nodes)))
        if node_indices is not None:
            if not isinstance(node_indices, list):
                return _safe_json({"ok": False, "error": "node_indices must be a list of integers"})
            indices = [int(i) for i in node_indices]

        applied: list = []
        skipped: list = []
        skipped_summary: dict = {}

        for i in indices:
            r = smoothness_engine.evaluate_collinear_handles_at_node(
                nodes,
                int(i),
                closed=closed,
                threshold_deg=float(threshold_deg),
                min_handle_len=float(min_handle_len),
                allowed_node_types=("curve",),
            )

            if not r.get("ok"):
                reason = str(r.get("reason", "skipped"))
                skipped_summary[reason] = int(skipped_summary.get(reason, 0)) + 1
                skipped.append({"nodeIndex": int(i), "reason": reason})
                continue

            node = nodes[int(i)]
            if bool(getattr(node, "smooth", False)):
                skipped_summary["already_smooth"] = int(skipped_summary.get("already_smooth", 0)) + 1
                skipped.append({"nodeIndex": int(i), "reason": "already_smooth"})
                continue

            applied.append(int(i))
            if confirm:
                try:
                    node.smooth = True
                except Exception:
                    skipped_summary["mutation_failed"] = int(skipped_summary.get("mutation_failed", 0)) + 1
                    skipped.append({"nodeIndex": int(i), "reason": "mutation_failed"})
                    applied.pop()

        skipped_truncated = False
        max_skipped = 400
        if len(skipped) > max_skipped:
            skipped_truncated = True
            skipped = skipped[:max_skipped]

        return _safe_json(
            {
                "ok": True,
                "target": {
                    "fontIndex": int(font_index),
                    "glyphName": glyph_name,
                    "masterId": str(master_id),
                    "pathIndex": int(path_index),
                },
                "params": {"thresholdDeg": float(threshold_deg), "minHandleLen": float(min_handle_len)},
                "dryRun": bool(dry_run) and (not bool(confirm)),
                "applied": applied,
                "skipped": skipped,
                "skippedTruncated": bool(skipped_truncated),
                "summary": {
                    "analyzedNodes": int(len(indices)),
                    "appliedCount": int(len(applied)),
                    "skippedCount": int(sum(int(v) for v in skipped_summary.values())),
                    "skippedSummary": skipped_summary,
                },
            }
        )
    except Exception as e:
        return _safe_json({"ok": False, "error": str(e)})

