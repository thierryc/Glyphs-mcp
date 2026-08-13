# LitSquare Metadata Contract

## Native Storage

Font, Glyph, and Layer scopes store a native property-list dictionary at `userData["com.litsquare"]`:

```text
{
  "schemaVersion": 1,
  "updatedAt": "2026-08-11T18:30:00Z",
  "settings": {...},
  "memory": {...},
  "status": {...},
  "notes": [...]
}
```

Any non-empty v1 object requires a positive integer `schemaVersion` and a UTC RFC 3339 `updatedAt`. `settings`, `memory`, and `status` are string-keyed dictionaries. Each note requires string `id` and `text`; `createdAt`, `updatedAt`, and `author` are optional strings. Omit empty sections.

Unknown top-level and nested fields are valid and must survive patches and migrations. Keys must be strings. Values may be dictionaries, arrays, strings, booleans, finite numbers, or binary data. Dates, nulls, arbitrary objects, NaN, and infinities are invalid. Binary values are native `NSData`; JSON projects them as `{"$binary":{"encoding":"base64","data":"…"}}` without changing native storage.

Inspector states are: `No context`, `Missing`, `Empty`, `Valid v1`, `Valid with warnings`, `Unsupported schema`, and `Invalid`. Reads never migrate. A future schema is read-only. Migrations must be explicit, sequential, and preserve unknown fields.

## Inheritance

Each scope remains authoritative for its direct data. Effective `settings` use a shallow overlay in Font → Glyph → Layer order. A narrower key replaces the entire parent value for that key. `memory`, `status`, and `notes` do not merge; inspect them with provenance. Path roles do not inherit.

## Path Roles

Store one role at `path.attributes["com.litsquare.role"]`. Absence means `unassigned`. Any non-empty string is valid; roles are case-sensitive. LitSquare writes trim leading and trailing whitespace while preserving internal whitespace. A non-string or whitespace-only stored value is `Invalid`. Never modify other path attributes.

The following names and meanings are guidance for common workflows, not a controlled vocabulary or allowlist:

| Role | Meaning |
|---|---|
| `body` | Dominant visible contour of a glyph or icon. |
| `detail` | Secondary visible contour within the design. |
| `counter` | True intentional typographic counter. |
| `cutout` | Knockout or subtractive artwork. |
| `accent` | Diacritic, dot, detached indicator, or emphasis mark. |
| `connector` | Bridge or shape joining otherwise separate forms. |
| `container` | Semantically distinct enclosure such as a circle, shield, or capsule. |
| `badge` | Small symbol-style status or attached overlay. |
| `foreground` | Visible form intentionally above another form. |
| `background` | Supporting visible form behind the main design. |
| `helper` | Retained construction or processing contour, not final semantics. |
| `reference` | Grid, alignment, optical-center, or measurement reference. |
| `erase` | Symbol-workflow semantic erase instruction; does not set Glyphs `mask`. |
| `hidden` | Excluded by an applicable workflow; does not set Glyphs built-in `hidden`. |

One selected path reports its role. Multiple paths report their shared role only when all match; otherwise they report `Mixed` with counts.

## Tool Transactions

- `get_litsquare_metadata` returns direct scopes, validation, provenance, and effective settings.
- `get_selected_litsquare_path_roles` returns explicit path targets, expected roles, structural fingerprints, counts, descriptions, and centering data.
- `patch_litsquare_metadata` uses RFC 7396 merge-patch semantics. JSON null deletes. It manages `updatedAt`, rejects direct schema changes, and supports `expected_updated_at` concurrency checks.
- `set_litsquare_path_roles` accepts any non-empty string, an empty string, or null. Strings are trimmed and an empty result removes the attribute. Every target must retain its glyph, layer, index, fingerprint, and exact raw expected role.

Writes require exactly one of dry-run or confirmation. Confirmed multi-path writes are atomic: any moved, changed, missing, or differently assigned path rejects the full transaction. Writes form one Undo step, verify native readback, notify the Palette, do not save, and report `fontSaved: false`.

## Palette Editing

All four tabs use one compact JSON text area without Context or State labels. Font, Glyph, and Layer project only `userData["com.litsquare"]`; an absent root displays blank and an explicit empty root displays `{}`. Paths projects the single `com.litsquare.role` attribute as `{\"role\": \"body\"}` and displays blank when unassigned. The namespace itself is never repeated in the editor.

Font scope has one target. Glyph, Layer, and Paths tabs aggregate the current selection: identical direct values display once, while differing presence or values display the subdued sentinel `mixedvalue`. A changed valid JSON value commits only when the text area loses focus and replaces every selected direct value atomically in one Undo step. Invalid JSON remains visible and causes no write. The compact footer reports target and validation information on the left; icon-only Full Metadata, Help, Copy, and Refresh controls sit on the right. Metadata commits recheck displayed values for staleness, manage `updatedAt` for non-empty roots, preserve unrelated user-data namespaces, and never save. Glyphs alone manages the native Palette disclosure state; the plug-in neither forces nor persists it, and collapse is not an MCP tool.

The Full Metadata control uses the `text.magnifyingglass` SF Symbol and toggles the active tab into a non-editable inspection projection. Font, Glyph, and Layer enumerate complete native `userData` dictionaries; Paths enumerates complete `attributes` dictionaries for selected paths only. Every selected target appears separately with family, glyph, layer, or path-index identifiers as applicable. Binary data and dates use presentation-only JSON markers, and unsupported native objects use diagnostic type markers with a footer warning. This mode never exposes a mutation path, never includes outline geometry or concurrency fingerprints, and never saves. Copy exports the visible projection. Pending valid LitSquare input completes its normal focus-loss commit before the mode changes; invalid or stale input prevents the change so the draft remains visible. Help explains that full metadata may include values owned by Glyphs or other plug-ins.

Keystrokes validate presentation only and never write individually. Escape restores the native baseline. Each valid focus-loss commit trims role edge whitespace, atomically replaces all selected values, verifies native readback, and creates one Undo step.

Outline recreation can discard custom attributes. Before Boolean operations, remove overlap, expansion, or decomposition, snapshot targets and roles. Compare the resulting paths, report missing metadata, and do not infer transfers.

## IconGrid Horizontal Center Policy

The universal path role remains at `path.attributes["com.litsquare.role"]`, but
it has no relationship to IconGrid positioning. IconGrid owns no path marker.
A layer stores one fixed horizontal coordinate in a separate native
property-list dictionary:

```text
layer.userData["com.litsquare.icongrid"] = {
  "schemaVersion": 1,
  "centerX": {
    "mode": "coordinate",
    "x": 521.5
  }
}
```

These domains are independently owned. Never use `com.leetsquare`, an
unnamespaced key, or `com.litsquare.icongrid.*` on a path. Preserve unrelated
user-data namespaces, all unrelated path attributes, and unknown fields in a
supported IconGrid schema.

Schema v1 accepts any finite absolute x coordinate. The coordinate is a
snapshot: moving or deleting artwork, changing components or semantic roles,
changing selection, and changing the advance width never update it. An absent
policy uses the reporter's configured position, whose default is the advance
center. Invalid policy data falls back to that unoverridden position.

The reporter can snapshot the selected-path union midpoint, the union midpoint
of all layer paths and components, or the current `layer.width / 2`. Only the
resulting x is stored; the source, bounds, and object identities are not.

`get_icon_grid_horizontal_center` returns the direct policy and schema state,
stored and resolved x, fallback state, advance and layer-content candidates,
and a fingerprint covering only the explicit layer target and IconGrid root.
`set_icon_grid_horizontal_center` accepts an explicit finite `center_x`.
`reset_icon_grid_horizontal_center` removes only `centerX`, deleting the root
when nothing meaningful remains. Neither mutation inspects or edits roles.

Both mutations require a fresh `expected_state_fingerprint` and exactly one of
dry-run or confirmation. Confirmed changes form one Undo step, verify native
readback, redraw, publish `com.litsquare.icongrid.changed`, do not save, and
report `fontSaved: false`. Future schemas are read-only. A malformed known-v1
`centerX` may be safely removed while retaining unrelated fields.
