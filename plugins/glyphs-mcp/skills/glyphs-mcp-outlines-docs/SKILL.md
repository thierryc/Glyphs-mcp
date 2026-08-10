---
name: glyphs-mcp-outlines-docs
description: Use this skill when the task is to inspect or edit outlines, components, anchors, selected nodes, cubic Bezier geometry, Tunni balance, signed curvature, curve quality, native candidate-session review, or curvature/candidate Reporter workflows in Glyphs while also using the bundled docs lookup tools to stay grounded.
---

# Glyphs MCP outlines and docs

Use this skill for path editing, component or anchor work, selected-node workflows, cubic curve geometry and quality review, and bundled Glyphs docs lookup.

## Core rules

- Prefer dedicated tools first.
- Use `execute_code_with_context` only for multi-step glyph-scoped work that is awkward with the dedicated tools.
- Keep any fallback script minimal, validate targets first, and bound output if needed.
- Use `docs_search` and `docs_get` instead of broad docs loading.
- Treat curve-quality results as measurements and conservative warnings, never as an artistic score or automatic pass/fail verdict.
- Re-read affected glyph state after mutation.
- Never auto-save the font.

## Workflow

1. Read the current state first with the smallest useful set:
   - `get_selected_font_and_master`
   - `get_selected_nodes`
   - `get_glyph_paths`
   - `review_tunni_geometry`
   - `review_curve_quality`
   - `get_curve_review_overlay_state`
   - `get_outline_candidate_state`
   - `get_glyph_components`
   - `get_glyph_details`
2. Prefer dedicated tools for the actual change:
   - `set_glyph_paths`
   - `add_component_to_glyph`
   - `add_anchor_to_glyph`
   - `review_collinear_handles`
   - `apply_collinear_handles_smooth`
   - `review_tunni_geometry`
   - `apply_tunni_balance`
   - `review_curve_quality`
   - `set_curve_review_overlay`
   - `get_curve_review_overlay_state`
   - `preview_tunni_balance_candidate`
   - `preview_collinear_handles_candidate`
   - `preview_italic_first_pass_candidate`
   - `preview_compensated_tuning_candidate`
   - `set_outline_candidate_overlay`
   - `get_outline_candidate_state`
   - `materialize_outline_candidate_session`
   - `review_outline_candidate_session`
   - `accept_outline_candidate_session`
   - `discard_outline_candidate_session`
   - compensated-tuning tools only when that workflow is explicitly requested
3. Use candidate sessions as the default outline-change workflow and require them for every multi-master or multi-glyph batch. For Tunni work, pass explicit master/path/curve-end targets to `preview_tunni_balance_candidate`; keep `grid_policy="font"` unless the user explicitly requests continuous coordinates. Direct `apply_tunni_balance` remains compatible for one explicit target only.
4. Enable the native Edit View comb with `set_curve_review_overlay(enabled=true)` after curve proposals and before mutation when visual judgment matters. Tell the user to inspect **View > Show Glyphs MCP Curvature** in Glyphs. Teal is positive signed curvature and pink is negative; curvature magnitude is placed along the path right normal, so correctly wound counters draw into their white interior. Native defaults are 51 samples per cubic, a `0.010` scale, and a `0.12em` normal clamp at `0.65` alpha. Use `get_curve_review_overlay_state` to confirm the last glyph/layer, stroke/clamp/cap counts, and omitted components. The native comb measures raw editable paths only. Do not use the deprecated PNG curvature overlay as the default curve-review workflow.
5. Review the difference-only Candidate Reporter before mutation. It leaves the normal Glyphs outline unobscured, draws only warm-yellow source/candidate difference regions, and turns those regions coral red when stale. If no manual edit is needed, call `review_outline_candidate_session`, dry-run acceptance, stop for approval, then confirm with the exact one-time token. If manual editing is wanted, dry-run and confirm `materialize_outline_candidate_session`, let the user edit the native layer, then re-review it. Never rely on LLM context to identify or delete candidate layers; use the persisted session metadata and `discard_outline_candidate_session`.
6. Only use `execute_code_with_context` when the edit spans several glyph-scoped steps and the dedicated tools would be less reliable or less clear.
7. When docs are needed, search first with `docs_search`, then fetch only the relevant page with `docs_get`.
8. After every mutation, re-read the affected glyph or layer state and report what changed.

## Curve geometry workflow

1. Resolve and report the exact `font_index`, `glyph_name`, `master_id`, and path-order `path_index`. Read the path first and preserve the reported Glyphs 4 `shapeIndex` only as additional context.
2. Call `review_tunni_geometry` for the explicit target. Omit `segment_end_node_indices` only when intentionally scanning every cubic; otherwise pass genuine integer curve end-node indices.
3. Call `review_curve_quality` for the same explicit target. Start with `include_samples=false`; request detailed samples only for a narrowed selection. Report signed and normalized curvature, inflections, degenerate tangents, spike warnings, join discontinuities, and omitted components without converting them into an artistic verdict.
4. Call `set_curve_review_overlay(enabled=true)` when visual judgment matters, direct the user to **View > Show Glyphs MCP Curvature**, and explain the teal-positive/pink-negative sign convention plus right-normal outside-ink placement. Call `get_curve_review_overlay_state` after a draw when bounded verification is useful. The overlay remains available when the MCP server is stopped.
5. If balancing is requested, create a candidate with the approved integer indices. Report `idealProposed`, authoritative grid-aligned `proposed`, post-grid imbalance, tangent drift, and any `no_safe_grid_candidate` result. JSON integer coordinates are expected on integral font grids.
6. Ask the user to inspect **View > Show Glyphs MCP Candidate**. Warm golden yellow marks only the symmetric difference; coral red plus `STALE` means the source changed. Identical geometry draws nothing over the glyph. Curvature is reviewed separately through **View > Show Glyphs MCP Curvature**. Materialize only when the user wants normal Glyphs editing.
7. Call `review_outline_candidate_session`; stop if it reports stale, topology, off-grid, or operation-external changes. Dry-run `accept_outline_candidate_session` with the issued token, then stop for explicit approval before `confirm=true`.
8. Re-read the affected path after confirmation. Verify only intended fields changed, candidate cleanup and any required backup succeeded, rollback did not fail, and the font was not saved.

For the compatible direct single-target path, dry-run `apply_tunni_balance`
with the same reviewed indices. Stop for explicit approval before `confirm=true`;
never use that shortcut for multi-master or multi-glyph work.

## Deeper references

- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
- [Project briefing](https://github.com/thierryc/Glyphs-mcp/blob/main/CODEX.md)
- [Tool profiles](https://github.com/thierryc/Glyphs-mcp/blob/main/src/glyphs-mcp/Glyphs%20MCP.glyphsPlugin/Contents/Resources/tool_profiles.py)
