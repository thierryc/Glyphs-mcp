# Small and petite caps implementation verification

Date: 2026-11-04. Source baseline: `88460d0847f5afb74009dfd4679439e5895dc7cf`.

## Implemented

- Discoverable `glyphs-mcp-small-caps` skill, helper contract, drawing/language
  guidance, dated research, UI metadata and license. Registered in the managed
  catalog and synchronized into the agent package (14 bundled skills).
- Self-contained native inspect/construct/verify helper. Fixed mappings and
  recursive dependencies are fingerprinted before construction; detached
  candidates are checked before attachment. Existing destinations and human
  corrections are preserved. Reports are task-local and create-only.
- Proof-specific bridge/sidecar protection, including the outer script guard.
  Known stopped edits can retain recovery while proofs open; active, prepared
  and uncertain operations still block. Advertised as
  `document.edit-tab.review.v1`. Closing protections remain unchanged.
- Read-only bounded installed-filter inventory through
  `filters.inventory.v1` / `get_status.nativeFilters`. No new executor or tool.

## Automated checks

The focused runtime, script snapshot/recovery, proof-tab, helper, filter inventory,
queue, catalog, skill routing, plugin/package and build tests completed with
**282 passed, 1 skipped**. Detailed output: `build/small-caps/final-tests.log`.
The skipped test was reported in the host-plugin test group.

The added snapshot integration test opens/retries a proof after a real script
workflow in the API-double harness, retains its exact snapshot, rejects an old
restoration generation after a manual edit, and restores the pre-run state with
a refreshed action. Other tests cover typed recovery, blocked/unknown operations,
closing, mappings, stale inputs, missing dependencies, fractional geometry and
human-edit preservation.

Skill quick validation and the native script scaffolder's static validation passed.
`sync_codex_plugin_skills.sh --check`, `check_lean_package.py`,
`check_skill_catalog.py`, and `git diff --check` passed.

## Native evidence

`scripts/qualify_small_caps_native.py` ran both through the plugin-free native CLI
and an existing native MCP script job on an empty disposable font in
**Glyphs 4.2, build 4202**. Ten derived bases/marks/composites were constructed
across two masters for `.sc` and `.pc`; open source outlines were held for review.
Checks included straight/cubic paths, anchors, mapped accented composites,
fractional node coordinates, source geometry preservation, manual-change
identification, repeated construction and an explicitly selected master subset.

An initial native attempt identified Glyphs 4's empty smart-component proxy
behavior; the helper was corrected and a regression test added. The failed
fixture was restored through its existing recovery workflow before the successful
attempt. No production font was used as an edit target or saved.

The live inventory found the installed `GlyphsFilterOffsetCurve`. Its instance
lacks the layer-local `filter` method required by the proposed adapter, so
**automated offset is not qualified on this build**. The helper refuses nonzero
offsets without qualification; the skill supplies an exact native UI handoff.
The CLI correctly reports unavailable filter inventory. Detailed live evidence:
`build/small-caps/native-live.json`; CLI output: `build/small-caps/native-cli.log`.

These are synthetic mechanical checks, not optical acceptance, interpolation
sampling, language shaping verification or measured productivity improvements.
Actual font tasks retain explicit pilot approval and designer review.

## Build and deployment boundaries

A local candidate was built at `build/small-caps/runtime`, with its manifest in
`build/small-caps/runtime-manifest.json`. The installed runtime is a release copy,
not an established development-link installation. It was not replaced or
restarted. The new server capabilities therefore remain unverified in the live
installed bridge; native helper tests used the existing script route.

Unrelated pre-existing changes to the workflow HTML and its JavaScript fixture
were left intact. Local-only routing files were not changed, staged or packaged.
No commit, publication, installation or font save was performed.

## Cleanup requiring explicit approval

The successful test workflow was kept without saving. Its generated
“Small Caps Qualification — disposable” font remains open and unsaved. Automatic
approval review rejected `close_document(..., unsaved_changes="discard")` because
explicit authorization to discard all its unsaved changes was absent. No indirect
cleanup or retry was attempted. Discarding/closing only that test font requires
the user's explicit approval; unrelated fonts remain outside cleanup scope.
