# Glyphs MCP execution and reproducible helpers

## Choose the route

- **Source file audit:** `source_hints.py` uses `glyphsLib.parser.Parser` to read
  saved syntax. It neither loads the incomplete format-4 font model nor saves.
  Requires Python 3 and glyphsLib. It includes actual backup/background records;
  it does not reconstruct opaque history embedded in userData.
- **Native audit:** `native_hints.py` requires Glyphs' Python runtime. Its
  `inventory(font)` takes an explicit native font. CLI mode binds an absolute
  saved source and verifies its file map before/after. It does not inspect live
  unsaved work. Its JSON must be stored outside the source.
- **Live unsaved audit:** native flags/hints are not currently typed read fields.
  Use the deliberate native script route on an authorized private copy. The MCP
  wrapper can mark even inspection dirty. Do not run this solely for read access
  on the canonical font and then needlessly Save/restore it.
- **Exports:** prefer typed `font_export` when its instance binding and generation
  options satisfy the project. Existing qualified project export workers can be
  necessary for custom precision, decomposition or Boolean preparation. Name
  that distinction and bind the saved source explicitly. Do not silently replace
  a failed/missing MCP capability with another operation.

CLI native audit (replace example paths with discovered absolute paths):

```sh
glyphs run --app '/Applications/Glyphs 4.app' --plugins '' '/path/to/native_hints.py' -- --source '/path/to/font.glyphspackage' --output '/private/proofs/native-hints.json'
```

The ordinary Python helpers require fontTools; raster comparisons also require
Pillow. OTS, a second rasterizer and AFDKO are optional external tools, not bundled
or installed by this skill. Report unavailability explicitly.

## Bind and read

Use `get_status` once for the retained connection: inspect jobKinds,
readCapabilities, nativeActions, scriptPreparationVersion and workflowCapabilities.
Use `list_documents` only to establish/re-establish the intended document; reuse
its ID. `read_entities` with exact layer IDs can verify width/outlineHash/metrics
without a script or Save. Requesting a nonexistent `hints` projection is not a
supported way to inventory hints. Avoid sidebar filters.

Before a custom native script require `script.native.v1`,
`script.recovery.snapshot.v1` and preparation version 3. Prefer a matching
advertised native action for an ordinary supported edit; there is currently no
advertised closed hint action. A composed hint operation is a deliberate script
route, not an invented action. Check current schemas/version before execution.

## Native script integration

Use the installed helper from its trusted skill path. For a complete inventory,
whole-script entrypoint code can be:

```python
import sys, json, importlib, hashlib
from pathlib import Path
root = Path(params['scripts'])
assert set(params['helperHashes']) == {'source_hints.py', 'native_hints.py'}
for name, digest in params['helperHashes'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == digest
sys.path.insert(0, str(root))
import source_hints, native_hints
importlib.reload(source_hints)
native_hints = importlib.reload(native_hints)
inventory = native_hints.inventory
assert len(font.glyphs) == params['expectedGlyphCount']
assert set(str(m.id) for m in font.masters) == set(params['masterIds'])
result = inventory(font)
with Path(params['output']).open('x', encoding='utf-8') as stream:
    json.dump(result, stream, indent=2, ensure_ascii=False)
print(json.dumps({k: result[k] for k in
    ['glyphCount', 'layerCount', 'hintCount', 'countsByClass', 'countsByScope', 'unavailable']}))
```

Resolve expected identities before execution; they are not magic constants.
Set `params.scripts` to this skill's absolute `scripts/` directory and `output`
to a new private report path. Supply `helperHashes` from the two trusted helper
files so a delayed dispatch rejects an intervening code update. The code runs
against the font supplied by the MCP
workflow, never `Glyphs.font`. `native_hints.py` does not save or close fonts.
The reloads prevent a persistent Glyphs Python session from using a previously
cached helper after a skill update. Review and bind trusted helper file hashes
when dispatching code. Keep the JSON local; do not print thousands of raw hint
records into chat.

Start `start_edit_workflow` with the copy's `document_id`, a retained unique
`idempotency_key`, `kind:'python_script'`, `mode:'apply'`, `auto_keep:false` and
`options:{source,params,entrypoint:'script',targets:[],summary}`. The request must
fit the server byte budget. A requested edit can run under existing task
permission; writing/reviewing code alone does not authorize execution.

Show the script warning once: arbitrary Python can access Glyphs and files;
pre-run recovery is whole-font, discards later edits/Undo, is session-local and
does not restore external effects. Preserve the original workflow/job IDs. Poll
`get_edit_workflow(include_review:false)`; do not re-dispatch a timeout or a queued
operation. Inspect the offered actions and use the current revision/token for
`respond_edit_workflow`. No card is needed for routine starts/polling.

Python returning successfully is not verified font preservation. For an audit,
compare the native report and source signatures. For an edit, preflight every
explicit glyph/layer and expected old hints before writing; verify all changed
and protected records afterward. A source change should preserve components,
anchors, backgrounds, metrics keys, fractional geometry, features and kerning.
Filter PS, TT and helper types explicitly; avoid a blanket `layer.hints=[]`.

Keep/Save ends pre-run recovery. An inventory request does not authorize a whole-font
Save merely to clear wrapper dirtiness. Keep without saving is available after a
successful verified inspection. Save only under explicit existing scope and only
on the intended document. Closing/discarding even a private test copy still needs
the required authorization; otherwise leave it open and report that state. Whole-font Restore requires authorization and a fresh
returned document ID. When authorization explicitly covers discarding the current
contents of a private test copy, its script Restore can return the clean pre-run
copy; close only that returned binding with `unsaved_changes:refuse`. Never apply
that cleanup recipe to the canonical font or unrelated recovery.
Failed/cancelled scripts can contain partial edits; they
must not be auto-kept. Do not settle another document's recovery to unblock work.

## Typed export and a tested binding limitation

Read instances with `{kind:'instances',limit:100}`, fields `['items']`; follow
opaque cursors. Use the returned exact ID, not a display name. Start one export:

```json
{
  "document_id": "EXACT_DOCUMENT_ID",
  "kind": "font_export",
  "options": {
    "instanceId": "EXACT_PERSISTENT_INSTANCE_ID",
    "format": "otf",
    "containers": ["plain"],
    "generation": {
      "autoHint": true,
      "removeOverlap": false,
      "useSubroutines": true,
      "useProductionNames": true,
      "decomposeSmartComponents": true
    }
  }
}
```

Use project-required generation settings rather than copying this example blindly.
Static default overlap removal can alter geometry; variable export fixes it off.
Poll the original `get_job(include_preview:false)` to artifact readiness and
review its report, source binding and exact manifest. Artifact jobs have no
`apply_job` step. `accept_job(destination:NEW_PRIVATE_DIRECTORY)` copies verified
staged files to the authorized location; it is not permission to upload them.
Do not save the font to “fix” an exporter error without a source-save reason.

During the LeftyNote format-4 qualification on Glyphs MCP 2.4.0/Glyphs4.2(4202),
typed export rejected the exact instance ID returned by `read_entities` as
unavailable in the saved source. That operation failed before export; no source
change followed. Treat this as a binding limitation to reconcile/report, not
proof that every format-4 export fails. Never guess another instance ID or repeat
an uncertain job. The native script inventory route was tested separately on a
private font copy; the repository's explicit saved-source worker remains its
qualified production export path. This skill does not modify the MCP installation.

## Comparison plan

`compare_fonts.py` accepts a JSON file with absolute input paths:

```json
{
  "glyphs": ["n", "o", "ntilde", "o.alt1"],
  "sizes": [12, 13, 14, 16, 18, 20, 24, 32],
  "phases": [0],
  "modes": [
    {"name": "existing", "file": "/private/current.otf"},
    {"name": "fresh", "file": "/private/fresh.otf"},
    {"name": "none", "file": "/private/unhinted.otf"}
  ]
}
```

For variable fonts add `location:{"wght":400}` for the raster proof and
`checkLocations:[{"wght":300},{"wght":400},{"wght":550},{"wght":700}]` for the
preservation checks. A default-only comparison does not qualify the axis.
Run with `--output` naming a nonexistent directory and `--label-font` pointing
to an installed system font for labels. Inputs are never rewritten.

The helper checks the **full glyph set** at each requested location (including
the raster location), UPM and effective CFF FontMatrix, and relevant
metric/layout/identity/variation tables. Unknown/out-of-range axes are rejected. It requires exact recorded paths and
metrics. Different contour starts or cubic decompositions can differ as recordings
while preserving fill; report that distinction and measure geometry if needed.
It never silently increases a tolerance or calls pixel similarity equivalent.
Failure writes `comparison.json` and stops before rendering.

Passing inputs receive proof-only CMap aliases for unencoded glyphs. The same
aliases are added to every option; a fixed baseline and shared bounds avoid
independent recentering or clipping. Original name/identity/geometry checks happen
before aliasing. The helper does isolated glyph proofs, not shaping; add real
shaped words and feature tests for provider/consumer acceptance. Large plans may
produce tall pages: split coherent glyph/size groups for review as needed.

Pillow uses its library-default rasterizer settings; do not claim you selected
specific FreeType load flags or that fractional coordinates prove distinct native
subpixel phases. Use a controlled engine harness for that test. The helper does
not implement CoreText, Windows, Adobe or OTS: those remain explicit additional
checks, and visual preference must be reviewed rather than inferred from counts.
