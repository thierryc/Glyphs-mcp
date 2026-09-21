# Native OpenType review and editing

Use the requested font and workspace. For an offline source, bind its explicit
path in the native script; inspect Glyphs' post-load interpretation and import
notices. For a dirty live font, use an authorized in-app native route and check
the intended native document before writing. A CLI load of the saved path does
not inspect unsaved edits. Do not replace a known target with the frontmost font.

1. Inspect the relevant ordered `font.features`, `font.classes` and
   `font.featurePrefixes`: names, source, automatic/disabled state and requested
   labels/notes. Bound output to the requested feature and its dependencies;
   report unexamined dependencies. Preserve manual code and collection order.
2. Use the development skill's [offline corpus](../../glyphs-mcp-development/references/development-docs.md)
   for unfamiliar native APIs. Read [qualified Glyphs 4 API notes](../../glyphs-mcp-development/references/glyphs4-api-notes.md)
   for native flags, compilation and export. Reuse excerpts already in context.
3. For an authorized change, show the exact source diff and intended effect,
   check referenced glyphs/classes, and modify only the explicit targets.
   Respect automatic generation; inspect generated changes rather than claiming
   that source stayed untouched after generation or compilation.
4. Prefer the closed `feature_compile` job when advertised; it calls
   `GSFont.compileFeatures()` and interprets the native
   success/error result explicitly. Retain the relevant feature, line, missing
   glyph and diagnostic text. Fix the source cause and rerun compilation; do not
   reinstall unchanged files to address a feature error.
5. If export is part of the task, prefer the closed `font_export` job when
   advertised, use a new output directory and the intended
   instance. Verify the actual binary and shape feature-on/off samples plus an
   unaffected control, with explicit script/language/direction when relevant.
   Compilation alone does not prove substitution, positioning or export behavior.

When the required closed capability is missing, report that the coordinated
installation needs updating; do not substitute a script. Create/revise a
workspace script only for genuinely unsupported or explicitly scripted work;
use the existing
development scaffolder only when a new artifact needs it. Native execution
follows the user's authorized scope. No feature-editing or Python MCP tool is
available. Native script changes do not acquire MCP job Undo/discard guarantees;
use the existing host behavior and verify preservation in the tested scope.

Report authored source, native compilation, exported binary and shaping results
separately, with script revision and host build. Missing binary or shaping
evidence is unverified, not a pass. Preserve unrelated source and user fonts.
Sampled Latin behavior does not establish a complete multilingual, variable-font
or stylistic-set audit. Adding a duplicate feature for a test does not justify
shipping it.
