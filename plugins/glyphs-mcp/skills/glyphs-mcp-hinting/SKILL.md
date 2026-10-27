---
name: glyphs-mcp-hinting
description: Inventory, diagnose and compare PostScript/CFF, CFF2 or TrueType font hinting with Glyphs MCP. Use for stems, alignment zones, manual versus automatic hints, and small-size rendering problems before scoped repairs.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs Hinting

Determine which hinting route improves the intended font in its actual renderers.
A count of hints, a sharper isolated pixel, or a sanitizer pass is not a quality verdict.
Keep the result as “retain” when benefits are mixed. Do not turn an irregular
handwriting or icon design into a regular text face merely to satisfy a hinter.

## Bind the evidence

Read project instructions and current source/release context. Record the intended
sizes, renderers, weights, protected glyphs, saved-source path/hash and whether
unsaved edits matter. Identify the exported outline table (`CFF `, `CFF2`, `glyf`);
`.otf`, `.ttf` and `.woff2` extensions alone do not establish hinting technology.
Research/writing-only requests need no live app. For native work reuse the exact
MCP document binding, or discover it once; never use the frontmost font implicitly.

For theory and current source links read [references/hinting-guide.md](references/hinting-guide.md).
For actual app execution, exports and recovery read
[references/mcp-workflow.md](references/mcp-workflow.md). Discover negotiated
capabilities and tool schemas rather than inventing a hinting native action.

## Gather the hints

Use `scripts/source_hints.py SOURCE --output NEW_JSON` for a **saved** Glyphs
package or flat source, using the raw parser, never a font-model rewrite. It
collects exact hint records from all foreground layers and existing backgrounds,
including backups/special layers, and separates production master counts.
It also records stems, zones, font/master/instance hint parameters and component
providers. Opaque archived data is explicitly outside the inventory.

Use `scripts/native_hints.py` to classify native `GSHint` objects and retain
node-link indexes, position/width, direction, options and native type flags.
Call `inventory(font)` with an explicitly supplied native font, or run the saved
source CLI described in the MCP reference. Corner/cap/brush helpers can share the
hint collection: **never clear `layer.hints` indiscriminately**. Preserve unknown
types. Unlinked coordinate hints are review candidates, not automatic defects.

The current MCP script wrapper can mark a font dirty even for inspection. Prefer
save-free typed reads for exposed fields. For a complete live/unsaved inventory,
use an authorized private copy and its exact ID; do not create a recovery decision
on the user's canonical document merely to collect read-only evidence. A saved
snapshot cannot certify unsaved live hints.

Run `scripts/binary_hints.py FONT... --output NEW_JSON` on actual deliverables.
It follows CFF subroutines in memory, inspects all private dictionaries, reports
CFF2 separately, and inventories TrueType programs/tables. Source hint counts
are not exported stem counts. Zero source hints can still yield autohinted CFF;
`autoHint=False` can still preserve manual hints. Verify the actual programs.

## Diagnose and trial

- Inspect representative straight/round stems and zones per master first;
  preserve compatible definition counts/order. Choose representative values,
  not a global average, arbitrary stem proliferation or mandatory sorting.
  Trial shared settings separately from glyph repairs.
- For CFF, compare current hints, fresh export autohinting, and genuinely unhinted
  output on detached copies. Manual PS hints exclude that glyph from auto;
  one incomplete manual hint is not supplemented automatically. Keep font-wide
  settings fixed in this experiment. Resolve the actual hint-source master and
  node correspondence; do not blindly duplicate hints into every master.
- Include alternates, accented consumers, components and controls. A component
  consumer can have independent hints. Decompose only a disposable copy when
  required for a diagnostic subset, before removing its providers; preserve
  advances/anchors and project precision. Never let the subset prune a target
  merely because it is nonexporting.
- For TrueType choose manual or automatic instruction pipelines explicitly.
  Preserve corner helpers and PS hints when editing only TT data. Do not run
  ttfautohint over manual instructions expecting per-glyph coexistence. Inspect
  `cvt `, `prep`, `fpgm`, glyph instructions, `gasp`, and variable `cvar` as relevant.
- CFF2 **can contain hints**. Audit its actual dictionaries/programs and test
  endpoints/intermediate locations. Do not infer variable support from a static
  tutorial or silently flatten a variable font. Current AFDKO `otfautohint`
  documents CFF2 support; check the installed tool/version/options before using
  it on a separate output, without geometry-changing options.
- Ghost/edge hints, masks, flex and TT deltas are format-specific; consult the
  guide before changing them. Missing extremes, overlaps or direction may
  explain failures, but this task does not authorize blanket outline cleanup.

## Verify the choice, then apply only authorized scope

Use `scripts/compare_fonts.py PLAN --output NEW_DIRECTORY --label-font FONT`
for repeatable exact preservation checks and FreeType proofs. Its JSON plan is
specified in the MCP reference. Compare geometry, metrics, identity and layout
first; a different outline is not a hint-only victory. The helper rejects drift
and records failed evidence. For variables supply explicit check locations.

Review 1x text as well as nearest-neighbor enlarged pixels: baseline/cap/x-height,
stem weight, counters, accents, diagonals, rhythm and clipping. Sample relevant
adjacent ppem sizes and subpixel positions. Keep the baseline/origin, font file,
variation location, antialiasing, hinting target, gamma/darkening and device scale
controlled and recorded. Do not crop or independently recenter variants. Pixel
counts measure change, not superiority; Pillow fractional positioning is not a
substitute for a controlled FreeType/DirectWrite phase test.

Test a second relevant engine. CoreText may react to standard stems while showing
no glyph-hint difference; matching Mac pixels cannot certify Windows or Adobe.
Load exact files without global installation where possible and defeat font-name
cache ambiguity with table/hash checks. Run OTS and applicable shaping/release
checks; validators do not assess optical quality.

Before a source mutation resolve exact glyph/layer IDs and expected old hint
records/counts for **all** targets. Use the supported MCP script route with
preflight before its first write; filter rendering hints by native type flags,
retain non-target types, unknown helpers and unrelated layers/data. A native
export autohinter is not a documented `GSLayer.autohint()` source-edit method.
Keep save/close out of scripts and use the MCP lifecycle under existing user
scope/authorization. Reconcile a timeout by its original operation ID; do not
replay an uncertain edit, import or Save. Restore a whole font only when authorized.

Re-read the saved diff and rebuild affected outputs after an accepted edit.
Report selected/retained options, exact font/source hashes, tested renderers and
sizes, failures/skips and pending visual/app review. Keep fonts/proofs local
when project policy requires it. This skill grants no publication, installation
or source redesign authority beyond the user's task.
