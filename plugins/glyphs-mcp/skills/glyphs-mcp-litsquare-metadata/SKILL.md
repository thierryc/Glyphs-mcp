---
name: glyphs-mcp-litsquare-metadata
description: Inspect, explain, dry-run, and safely change LitSquare metadata and semantic path roles in Glyphs. Use when a task mentions com.litsquare metadata, LitSquare settings, memory, status, notes, inheritance, selected-path roles, icon centering, or metadata preservation across outline operations.
---

# LitSquare Metadata for Glyphs MCP

Use the typed LitSquare tools. Treat Glyphs' native dictionaries and path attributes as authoritative; JSON is only their transport projection.
The Glyphs MCP Metadata Inspector uses Glyphs' native Palette disclosure control; the plug-in does not force or persist its open/closed state. Every tab uses the same compact JSON text area. Font, Glyph, and Layer edit only the direct `com.litsquare` value; Paths projects `com.litsquare.role` as `{\"role\": \"body\"}` and shows blank text when unassigned. A changed valid value commits once when the text area loses focus. Invalid JSON remains visible and causes no mutation; Escape restores the native baseline. The `text.magnifyingglass` footer control toggles the active tab into a read-only JSON projection of complete Font/Glyph/Layer `userData` or every selected path's complete `attributes`; multiple targets are listed separately with compact identifiers. Diagnostic markers represent native values JSON cannot express directly. The remaining footer controls provide Help, Copy, and Refresh. Palette edits are document-bound, undoable, and never save a font.

Read [references/metadata-contract.md](references/metadata-contract.md) before any mutation or role recommendation.
The canonical repository copy is [metadata-contract.md](https://github.com/thierryc/Glyphs-mcp/blob/main/skills/glyphs-mcp-litsquare-metadata/references/metadata-contract.md).

## Workflow

1. Resolve the exact `font_index`, glyph name, layer ID, and selected paths. Stop on ambiguous glyph or layer selection.
2. Call `get_litsquare_metadata` with inheritance enabled. Read the direct Font, Glyph, and Layer scopes plus effective settings and provenance.
3. When paths matter, call `get_selected_litsquare_path_roles`. Retain every returned glyph name, layer ID, path index, fingerprint, and expected role.
4. Validate schema support and property-list compatibility. Do not mutate invalid data or a future schema.
5. Propose the smallest change. Preserve unknown LitSquare fields, unrelated `userData` namespaces, and every unrelated path attribute.
6. Call `patch_litsquare_metadata` or `set_litsquare_path_roles` in dry-run mode. Present every replacement explicitly.
7. Confirm only after the user approves the dry-run. Never infer a low-confidence role and never copy inherited values into a narrower scope merely to make them explicit.
8. Read the affected metadata or roles again. Report verified results and `fontSaved: false`; never save automatically.

### IconGrid fixed-centering requests

IconGrid centering is independent from semantic roles. For “center the grid on
the selected paths”:

1. Read the selected paths with `get_selected_litsquare_path_roles`; use each
   returned finite `bounds` value only, and ignore its role for centering.
2. Compute the midpoint of the selected paths' union bounds. This coordinate is
   a one-time snapshot and must not be recalculated after artwork moves.
3. Read the layer with `get_icon_grid_horizontal_center` and retain its fresh
   `stateFingerprint`.
4. Preview `set_icon_grid_horizontal_center` with the explicit finite
   `center_x`, then apply only the identical confirmed preview.
5. Read back the stored and resolved x. Never save.

For layer-content or advance centering, use the corresponding candidate from
`get_icon_grid_horizontal_center` and pass its x explicitly to the same Set
tool. Reset removes only the layer's IconGrid policy. No IconGrid operation
reads, assigns, removes, or edits semantic roles.

Palette multi-selection is a direct replacement workflow: identical selected roots display once, differing roots display `mixedvalue`, and committing valid JSON replaces every selected direct root atomically. This is intentionally distinct from the agent-facing merge-patch tool.

## Safety Rules

- Use `com.litsquare` for general Font, Glyph, or Layer metadata,
  `com.litsquare.role` for path semantics, and `com.litsquare.icongrid` only for
  the separately owned layer IconGrid policy. Never use `com.leetsquare`, an
  unnamespaced key, or an IconGrid-specific path attribute.
- Never persist the root metadata object as a JSON string.
- Never change `schemaVersion` through a patch. Run only an explicit, supported migration path.
- Use JSON null only as a merge-patch deletion instruction. Native stored values cannot be null.
- A role may be any non-empty string. Leading and trailing whitespace is trimmed; internal whitespace and case are preserved. Remove a role with null or an empty string. Never store the presentation values `unassigned`, `mixed`, or `invalid` automatically.
- Keep semantic `hidden` and `erase` independent from Glyphs' built-in `hidden` or `mask` attributes.
- IconGrid v1 stores one finite absolute x coordinate in `centerX` coordinate
  mode. Artwork, selection, roles, and later advance-width changes never update it.
- Reject IconGrid writes to future schemas. A malformed known-v1 `centerX` may
  be removed safely without replacing unrelated supported-schema fields.
- Warn before Boolean operations, overlap removal, stroke expansion, decomposition, or other outline recreation. Snapshot roles first, compare afterward, and report losses without guessing transfers.
- Reject secrets, credentials, tokens, private keys, and complete conversation histories. Store only concise, task-relevant, non-sensitive memory or notes.

## Role Decisions

Recommend a role only when the contour's purpose is clear from the outline and task context. Explain uncertain cases instead of writing them. Custom role strings are valid and case-sensitive. Semantic roles never control IconGrid positioning.

The contract reference lists common roles as guidance, not an allowlist. Path-role writes must use the exact read-time targets so stale or replaced paths fail atomically.
