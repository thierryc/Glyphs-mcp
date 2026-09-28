# Beta 8 milestone 8 — Exact kerning and language proofing

Status: source/native qualification and the installed 72-case editor lifecycle suite pass. The new runtime and desktop app are installed and loaded. Actual Codex proof and exact-edit workflows pass. Glyph-pair native UI Undo/Redo passes; group-pair UI Undo and the new pair-card visual gate remain unresolved. See the [combined candidate report](../beta8-release-candidate/README.md). The original installation blockage below is historical.

This milestone adds `kerning_edit` and `kerning_proof` through the existing twelve tools. No new execution mode, recovery system or public tool is added. There are 1–100 explicit assignment/removal entries per typed batch, with exact master, direction, glyph/group sides, fractional values and zero distinct from deletion. Preparation uses scheduled native reads without a font copy or worker. Existing selective recovery and Keep/Save are retained.

Proof reads use a pinned MIT pair dataset with 24 upstream language tags. Primary Unicode mapping is built in pages of at most 256 glyphs and retains only the dataset alphabet. Ambiguous and missing mappings are reported, never guessed. Candidate pages scan at most 256 pairs and return at most 100. Proof strings are unshaped characters. Exact storage and native effective coverage are evidence for inspection, not proposed values or mandatory corrections. Existing collision analysis remains separate.

## Tests before implementation

- `tests-before.txt`: original exact-edit suite failed as expected (28 failed, 3 passed; the three existing target errors were not implementation evidence).
- `proof-tests-before.txt`: proofing interface and pinned dataset were absent.
- Native testing exposed duplicate document Undo registration during glyph-owned history. The added failing test is retained in `native-registration-test-before.txt`; the adapter now suppresses the native second registration while retaining the exact inverse on the intended manager.
- The existing convenience lookup used a numeric absence threshold. `large-value-test-before.txt` demonstrates the issue; direct native dictionary reads now retain stored values above that threshold. Native qualification includes 2,000,000.5 and ordinary fractional values.
- Conversation and package regression baselines are retained separately. Cards and text identify pair, master, direction and exact absence/removal semantics; rendered strings remain text.

## Qualified source evidence

- `regressions.txt`: 329 relevant protocol, bridge, sidecar, lifecycle, kerning, native preparation, conversation, recovery, routing and build/package tests passed.
- `native-exact-glyphs.json` and `native-exact-glyphspackage.json`: 48 cases each, covering all four glyph/group combinations, three directions, fraction/zero/removal/large value, untouched controls, native Undo/Redo and selective recovery. These use real Glyphs native classes in standalone processes; they do not substitute for actual-editor integration.
- The pinned dataset can be reproduced with `python3 scripts/vendor_kerning_pairs.py --check`; complete MIT notice, source revision, input hashes and normalization recipe ship with it. Historical v1 assets are unchanged.
- The broad unrelated suite was interrupted while its 10,000-history fixture stalled in a filesystem open. It is not counted as passing. The relevant focused suite above completed normally.

## Performance

See [benchmarks](BENCHMARKS.md), `benchmark-summary.json`, `matrix/` and `proof-matrix/`. There are 60 assignment runs and 20 fresh proof processes covering 60 language-filter traversals. Final measurements use an immutable candidate source copy; exploratory results were moved under ignored build output after discovering native edge cases.

The measured end-to-end assignment medians are approximately 0.30–0.32 seconds for both script and typed workflows. This is not evidence of a general speedup over native scripting. Typed edits add precise request validation and selective recovery. The existing supervision/polling interval dominates these small workloads. Typed selective restoration takes about 0.25–0.26 seconds including polling; whole-font script reload is faster on these tiny fixtures but restores a different scope and clears history. No limit or responsiveness guarantee is inferred from these samples.

Longest chunk measurements cover scheduled native preparation/application, not every synchronous save/load call or visual frame rate. GSFont fixture serialization, actual editor Save and installed-client latency remain distinct measurement boundaries.

## Original milestone delivery boundaries (historical)

The existing beta-8/build-50 development target is retained. Update only the MCP component; preserve companion installations, port, auto-start, project settings and unrelated fonts. Dactylotype is not a mutation fixture. Source, build, installed and loaded identities must agree before completion. Publication and commits are excluded; stop after this milestone.

The lean candidate built successfully (`build-manifest.json`). The installer stopped progressing while staging a private runtime copy, before creating its journal or moving any live target. The installed receipt remains equal to `receipt-before.json`; `receipt-during-stalled-install.json` is an observation of that unchanged receipt, not proof of installation. The old sidecar remains reachable with its prior identity. The independent desktop build also stopped progressing in `clang-stat-cache`. Termination was requested, but both child processes remained in uninterruptible filesystem waits. A retry correctly refused the held installation lock; no lock was bypassed.

Glyphs was quit only after all five open documents were confirmed saved and clean and no operations were active. Reopening it was then blocked by the locked Mac. No M8 editor fixture has been mutated, and no actual-editor or Codex M8 edit is counted as passed. The original Dactylotype was neither edited nor saved by this milestone.

## September 28 combined-candidate follow-up

The subsequent user request authorizes consolidation, commits, local installation
and signing. `editor-glyphs.json` and `editor-glyphspackage.json` contain 36 passing
actual-editor cases each. `codex-connector-proof.json` completes 22 bounded pages
through the installed Codex connection. `installed-native-ui-followup.json` records
exact-edit preview/apply/Keep/Save, successful glyph-pair UI Undo/Redo, the unresolved
group-pair UI Undo observation, unchanged outline/width controls and clean final
documents. The test pair values were restored. No original font was edited.

Do not mark milestone 8 fully qualified until the group/document native history
and new pair-card visual acceptance are resolved. The combined source and signed
local candidate remain preparation artifacts, with no Beta 8 publication.
