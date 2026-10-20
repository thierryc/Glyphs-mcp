# Font View sidebar filters

Use this reference for Font View categories, Smart Filters, List Filters and
`Invalid filter in sidebar` warnings. These are separate from outline-processing
plugins in the Filter menu and export Filter custom parameters.

## Automation: prefer explicit glyph targets

Do not use sidebar predicates to discover or select targets for an MCP edit.
Read glyph names and supported metadata, build an explicit name list, resolve
owning layer IDs and surfaces, and submit that fixed manifest. Capture a
user-requested selection once before preparation; never follow live UI selection
during the edit. See [script targets](python-scripts.md#request-and-targets).

This does **not** disable automatic category/script counts. Valid predicates can
still produce native evaluation errors during edits. Do not promise that choosing
All, closing the sidebar, or batching interface updates prevents these alerts.

`GSSidebarItem.suppressCount` is documented in installed Glyphs 4 headers to
suppress calculations for unselected items. Temporary suppression is an
**experimental mitigation**, not a production MCP capability. It does not cancel
already queued work or protect selected predicates. Sidebar flags need exact
restoration; the script recovery copy does not establish UI-state recovery.

Run the repository experiment with
`python3 scripts/run_sidebar_count_experiment.py`. It uses separate plugin-free
processes and synthetic fixtures, requires an attached Font View/sidebar and
records blocked qualification if that UI is unavailable. It never switches to
the working session. No production suppression is enabled. A clean baseline
means **not reproduced**, not evidence of an effective mitigation.

## Choose the expression's destination

- **Smart Filter editor:** prefer the built-in rules for ordinary conditions,
  such as Case is Lowercase and Category is Letter, combined with All. Its Custom
  rule accepts a glyph predicate expression; check the actual editor and build.
- **Stored native sidebar predicate / `GSSidebarItem.predicateFormat`:** a plain
  Foundation `NSPredicate` format string. For lowercase letters:
  `case == 2 AND category == "Letter"`. Do not add a `$[...]` wrapper or assume
  that feature-token constants are available in this raw evaluation path.
- **OpenType feature token:** `$[case == lower AND category == "Letter"]`.
  The token processor understands symbolic constants such as `lower`, `upper`
  and `smallCaps`. Their presence in the handbook does not establish support
  in every consumer of a predicate string.
- **Python:** compare `glyph.case == GSLowercase` and
  `glyph.category == "Letter"`, using the imported GlyphsApp constant. Python
  attribute access does not establish an equivalent native predicate key path.
- **List Filter:** explicit glyph names, rather than a predicate expression.

The pinned Python SDK defines GSNoCase=0, GSUppercase=1, GSLowercase=2,
GSSmallcaps=3, GSMinor=4 and GSOtherCase=5. Category and subCategory are string
properties; case is a separate numeric property. Do not replace lowercase case
tests with `subCategory == "Lowercase"` as a generic Glyphs 4 repair.

## Diagnose before rewriting

The warning alone does **not** prove malformed syntax or an agent-authored
filter. It can refer to a native category entry. First establish the app
version/build, the exact sidebar entry, whether it is built-in or custom, and
the destination in which the expression was used. Preserve the expression and
the complete native exception, including any preceding diagnostic.

Check parsing and evaluation separately: Foundation's format parser does not
validate that a property exists on the objects evaluated later. A nil predicate,
exception, or all-false result must not be reported as successful filtering.
For a native check, include expected matches and nonmatches, and compare actual
names, not just a successful process exit. Some native getters/evaluation paths
log an error and return false without raising a Python exception.

Then verify the entry in the **actual Font View** and intended live font.
Disposable CLI objects establish only their own behavior, not the live sidebar's
counter, missing-glyph coverage, migrated filter storage, or dirty font state.
If parsing/evaluation pass but the sidebar warns, retain that distinction and
investigate the native diagnostic rather than inventing a replacement string.
Rebuilding a custom rule with the native editor can establish the syntax emitted
by that build; changes to filters/preferences still follow the user's scope.

Do not guess a native `glyphInfo.case` key path from Python's `glyph.glyphInfo`.
Do not delete filters, reset preferences, change glyph metadata, save or restart
as part of a read-only diagnosis. The MCP metadata projection's supported fields
are documented separately in [metadata reads](metadata-reads.md); an unavailable
projection field is not evidence that the native property is absent.

## Qualified observation: Glyphs 4.2 (4202)

On 2026-10-15, an isolated, plugin-free `glyphs run` process loaded
`/Applications/Glyphs 4.app`. A detached GSFont contained `a`, `A`, `a.sc`,
`one` and `acutecomb`; no editor document was opened, edited or saved.

`case == 2 AND category == "Letter"` parsed and matched **only `a`**.
`GSSidebarItem.setPredicateFormat_` also retained that predicate. An unattached
sidebar item's count returned -1, so this is **not** a verified Font View result.
Using bare `lower` in raw NSPredicate evaluation logged an undefined-key error;
`glyphInfo.case` logged an undefined `glyphInfo` key. Neither matched `a`.
The subCategory replacement also failed to match `a`.

Reproducer and captured results:
`reports/sidebar-filters-20261015/` in the repository. This single-build check
does not reproduce or explain the user's original sidebar warning. Do not
describe the original numeric expression as invalid based on that warning.

## Sources and retrieval

- [Glyphs Handbook: Filtering Font View](https://handbook.glyphsapp.com/filtering/)
  documents native rules, nesting and the Custom rule. Offline corpus ID:
  `handbook:036_font-view_filtering.md`.
- [Glyphs Handbook: Glyph Predicate Tokens](https://handbook.glyphsapp.com/layout/tokens/#glyph-predicate-tokens)
  documents feature-token syntax and symbolic case constants. Offline corpus ID:
  `handbook:090_layout_feature-code_layout_tokens.md`.
- [Glyphs Python API](https://docu.glyphsapp.com/#gsglyph) and pinned SDK revision
  `c0352321d30a06006f18e94d600f5caf43d06f1b` document glyph case; SDK
  `ObjectWrapper/GlyphsApp/__init__.py` defines the numeric constants.
- [Apple: Predicate Format String Syntax](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/Predicates/Articles/pSyntax.html)
  explains parsing, literals and the lack of semantic type checking.

Use the development skill's [offline helper](../../glyphs-mcp-development/references/development-docs.md)
for these corpus IDs. Keep this project qualification separate from the pinned
upstream corpus; do not rewrite vendored source documentation to add observations.
