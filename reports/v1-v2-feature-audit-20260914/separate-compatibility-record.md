---
title: Lean master compatibility
description: Native evidence, explicit ordinary-master repairs, and disposable-font qualification.
---

This worktree adds master compatibility to the seven-tool sidecar. It changes
operation-specific state/read/write hooks and leaves `native_undo.py` unchanged.
The existing `start_nodes` correspondence algorithm is also unchanged.

## Contract

`read_entities` accepts one glyph with the `compatibility` field. Native
`mastersCompatible` and opaque `compareString()` results are separate from
indexed explanatory comparisons. Reads include master/layer IDs, special-layer
attributes, excluded backups, ordered paths/components, node counts/types,
directions and anchor names. Special relationships remain unresolved.

`start_job(kind="master_compatibility")` supports `inspect`, `normalize` and
`reorder`. Only inspection can scan the entire saved source. Repairs require
explicit glyph and ordinary-master layer IDs. Normalization calls native
`correctPathDirection()` on detached layers; reordering uses a complete supplied
permutation. Start-node correspondence remains a separate job and requires a
clean saved source after any reviewed intermediate edit.

A single `reorder` change contains the mixed shape permutation, native
reversal/start instructions, exact target guards and the Glyphs build used to
prove replay. The bridge checks that build before writing. New/deleted objects,
changed native segments, uncertain correspondence, changed target metadata, and
unrestorable native operations produce no patch for that glyph. The bridge
replays existing objects through the current native undo registration; it never
reruns normalization against the live font.

Native reversal retains hint node references but can leave cached hint indexes
stale. The operation refreshes those caches by reassigning the same hint objects
through the native layer collection. Exact guards cover both references and
indexes, as well as hint positions, widths, options, scale, alignment and metadata.

Capabilities are additive: `glyph.compatibility.v1` and `layer.reorder.v1`, plus
the three advertised job modes. Older bridges are rejected before repair
preparation and again before application. The public interface and wire
protocol remain revision 1; the catalog still contains seven tools.

## Bounds and interpretation

Detailed evidence is limited to 32 layers, 64 shapes/anchors per layer, 4096
nodes per glyph, and bounded metadata. Exceeding a limit marks evidence
incomplete and avoids the unbounded native compatibility call.

Automatic repair and `reorderHash` use a tighter 256-node layer limit, with at
most 64 shapes/anchors/hints and an aggregate metadata bound. An isolated native
probe measured about 140 ms for one 4096-node exact guard. A 512-node
guard/write/readback sequence exceeded 50 ms under load; the 256-node limit
leaves headroom for the editor while remaining below the threshold in isolation.
Installed-editor main-queue timing still requires its separate live gate.

An identity permutation and a repeated normalization can be zero-change jobs.
Repeating a newly prepared `[1,0]` permutation intentionally swaps again; it is
relative to the current order. Inspection reports are explicitly inapplicable.
After applying, reinspect. “Requested repair applied” and “all examined layers
compatible” are separate claims, and technical compatibility says nothing about
interpolation quality.

## Reproducible fixture and qualification

The baseline is `src/glyphs-mcp/tests/fixtures/MasterCompatibilityTest.glyphs`,
with its companion `.expected.json`. The native generator uses three fixed
weight master IDs, a fixed axis ID, fractional geometry, hints and node metadata.
It includes compatible, shifted, reversed, reordered, structurally incompatible,
ambiguous, intermediate, alternate and backup cases. Volatile per-glyph save
timestamps are omitted so repeated generations are byte-identical.

Run the generator and isolated native tests with no plugins:

```sh
glyphs run --quiet --app '/Applications/Glyphs 4.app' --plugins '' scripts/generate_master_compatibility_fixture.py -- /tmp/MasterCompatibilityTest.glyphs
glyphs run --quiet --app '/Applications/Glyphs 4.app' --plugins '' scripts/qualify_master_compatibility_native.py
```

Compare the generated file and manifest with the committed baseline. The native
gate checks diagnostic agreement, exact geometry/object/hint preservation,
native Undo/Redo, bridge discard, cancellation, dirty-source rejection, no-op
repeats and unsupported cases. It writes `build/master-compatibility-native.json`.

For editor qualification, first run
`scripts/qualify_master_compatibility_live.py prepare-copies` using the sidecar
Python environment. Open only the printed disposable paths. For each mode
(`--mode normalize` and `--mode reorder`), run `apply`, select each affected glyph
and invoke native Undo, run `verify-undo`, invoke native Redo for each glyph,
run `verify-redo`, then `discard`. Run `finish` after both modes. The runner
selects exact paths and allows unrelated documents to remain open. It checks
source hashes, stale/dirty rejection, cancellation, native evidence, exact target
guards and the existing p95 < 50 ms / maximum < 200 ms responsiveness gates.

As of this implementation, the isolated native gate and 306 relevant regression
tests pass. The packaged sidecar also prepares all three job modes through a real
plugin-free native worker, including all 15 fixture glyphs for inspection;
`scripts/qualify_master_compatibility_worker.py` runs these checks and
`build/master-compatibility-worker.json` records them. Installed-editor
qualification remains pending. At the time of that attempt, this worktree
targeted 2.0.0 while the host used the separate desktop candidate and Dactylotype
had unsaved changes. A staging
attempt was restored from backup without restarting Glyphs. The original
installation and the open document's dirty state and generation were verified
unchanged. Do not treat this feature build as a qualified release.

On 10 September 2026, the host's Glyphs 4 components were upgraded to
**2.0.0 Beta 1, build 43** from `build/milestone7/desktop`. Installed file
identities and bridge/worker availability were verified. This installation
check does not qualify the separate master-compatibility feature build.
