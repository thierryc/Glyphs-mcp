---
name: glyphs-mcp-italic-first-pass
description: Create a guarded experimental italic or oblique construction draft from Roman glyphs for explicit designer review.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP italic first pass

A mechanical construction is a draft, never a finished italic.

## Evidence and judgment

1. Call `get_server_info`, require `data.apiMajor == 2`, resolve one font with
   `list_documents`, then search `search_knowledge` for current Glyphs slant,
   transform, component, and italic-angle behavior. Retrieve the cited entries
   you rely on with `get_knowledge`.
2. Use `read_document` to resolve exact Roman source masters, italic target
   masters, glyphs, layers, bounds, ownership, geometry counts, components,
   anchors, alignment, and compatibility evidence.
3. Default the Glyphs source angle to positive 12° only when the user gives no
   angle; exported `slnt` and `post.italicAngle` normally use the opposite sign.
   Calculate the shear around an explicit pivot and state whether advance,
   origin, sidebearings, or optical centering is intended to remain fixed.
4. Never overwrite a developed italic. Targets must be empty or explicitly
   approved bootstrap copies. Preserve topology, live components, anchors, and
   non-target metadata; refuse ambiguous component chains or correspondences.

## Construction lifecycle

Generic `translate` and `set` operations may express positioning and explicit
metrics, but an affine shear is not part of the typed operation registry. Use
`execute_python(mode="staged_document")` for that unsupported construction on
a detached font. Keep exact document/master/glyph/layer scope, return the
immutable semantic preview, and apply it only through `apply_change`.

After application, use `read_document` to inspect the exact layers and proof
strings. Check overshoot, rhythm, joins, counters, diagonals, punctuation,
marks, components, interpolation, and spacing. Report the angle, pivot,
translated distances, exceptions, and limitations. Never call `save_document`
automatically.
