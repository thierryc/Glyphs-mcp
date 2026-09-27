# Real task qualification, 26 September 2026

Status: installed typed workflows passed; built native scripting passed in an
isolated Glyphs process. The candidate's installed editor/chat scripting gate
remains pending explicit installation/relaunch permission. This is not a release
qualification or a new implementation plan. No runtime code was changed.

## Real font and preservation

Tests used an owned copy of Dactylotype: 423 glyphs and nine masters, with curves,
components, anchors, existing groups, kerning and features. All edits targeted
the exact Regular master `0578215A-7423-43EB-8AD4-4C95A1C78DFA`.

The original source package has the same before/after hash
`sha256:38e15d52b86817f7e3273ae01d64fbde6c2656abff2c713a70c1b3ef66bc13be`.
Its live binding remains clean at generation 623. The editor test copy was closed
without saving its final test session; all five typed jobs are discarded and
the installed bridge reports zero active operations. See
[original preservation](original-preservation.json) and
[final installed state](installed-final-state.json).

## Actual editor and chat: installed Beta 7, build 49

These tests used the installed MCP tools from this Codex conversation, real
Glyphs 4.1 (4107) documents, actual NSDocument saving, and native editor Undo/Redo.
They did not use a mock adapter. The installed runtime does not advertise
`script.native.v1`; therefore these results qualify its retained typed routes.

| Task | Actual change and verification | Recovery |
| --- | --- | --- |
| Path editing | Regular `o`, path 0, node 0: `(816.875, -19.953)` to `(824.125, -23.453)`. Every other node in that path was preserved; 13 control layers retained hashes, widths and metric keys. | Native Undo/Redo restored geometry; whole-job discard restored checked layer hashes and metrics. See metadata caveat below. |
| Spacing | H, n, o proportional spacing: advances `1359.68 → 1483.110609753689`, `1150.78625 → 1252.2153923535816`, `1092.03521 → 1190.1248601095244`. Applied widths and outlines matched the proposed patch; 11 control layers were unchanged. | Native Undo on o affected only o; Redo and whole-job discard passed. Actual outline was inspected in the editor. |
| Kerning | Regular A/V `-300.25 → -177.8762353373504`, T/o `-280.5 → -98.74719348375515`. Both reached measured clearance 400; 19 control pairs, glyph groups and 14 control layers were unchanged. | Whole-job discard restored exact values. A separate native kerning Undo/Redo check was not performed. |

Two prerequisite Save-and-continue actions completed through the actual editor,
with clean-state and source-hash receipts. The preserving-width spacing test and
the initial 5.125-clearance kerning test correctly made no changes. Negative
seed kerning values alone did not create collisions in this font; increasing the
requested clearance to 400 exercised actual correction. This verifies sampled
clearance arithmetic, not optical kerning or perfect spacing quality.

Full requests, values, save receipts and restoration evidence:
[installed typed evidence](installed-typed-evidence.json).

## Built native scripting on the real font

Fresh isolated native processes ran the real built candidate bridge and sidecar
against disposable `.glyphs` and `.glyphspackage` copies. This used the existing
native harness and conversation state machine, with GSFont serialization as its
fixture save adapter. It did not use installed editor saving, HTTP transport or
rendered chat cards. Module origins are recorded in each result; all 99 source /
built Python pairs match in [candidate identity](candidate-identity.json).

Both formats passed all three tasks:

- Per-target path edit with exact fractional coordinates.
- Per-target spacing on H/n/o: move paths, components and anchors +12.5 X and add
  20.75 to each advance, preserving contour geometry. This is an explicit numeric
  adjustment, not a replacement for the typed optical-spacing algorithm.
- Whole-script kerning with `targets:[]`: set exact A/V and T/o values and verify
  every other stored kerning value, resolving runtime glyph IDs to glyph names.

Across each task, checks cover six glyphs in all nine masters, unselected
backgrounds, metrics keys, all stored kerning, all glyph groups and features.
Clean runs issued zero saves. The dirty-baseline spacing run issued one save.
Preparation did not execute source. Saved-version restoration returned the
checked content, cleared native Undo, returned a new document binding, and made
no save call. The path test also changed the family name after execution and
verified that restoration replaced that later edit.

There are 190 assertions per format (380 total, including repeated control-layer
checks), not 380 independent end-to-end scenarios. Evidence:
[package run](candidate-native-glyphspackage.json),
[single-file run](candidate-native-glyphs.json),
[reproducible test driver](qualify_real_tasks.py).

## Timing observations

One successful run per task and format; these are observations, not medians or
a benchmark against equivalent direct loops. Preparation includes readiness
polling. Run includes authorized prerequisite save when dirty, dispatch and
completion polling. Verification and restoration are excluded. CLI startup,
HTTP/model latency, UI frame rate and peak memory were not measured here.

| Format | Task | Preparation, s | Run/poll, s | Longest scheduled native chunk, ms |
| --- | --- | ---: | ---: | ---: |
| glyphspackage | Path, 1 target | 0.313 | 0.232 | 34.87 |
| glyphspackage | Spacing, 3 targets, dirty baseline | 0.097 | 0.607 | 25.20 |
| glyphspackage | Kerning, whole script | 0.114 | 0.224 | 26.73 |
| glyphs | Path, 1 target | 0.311 | 0.199 | 3.56 |
| glyphs | Spacing, 3 targets, dirty baseline | 0.272 | 0.194 | 8.11 |
| glyphs | Kerning, whole script | 0.252 | 0.204 | 4.73 |

These actual-font operations are quick in isolation, but package work matters
even for a one-target edit. The 34.87 ms scheduled chunk exceeds the earlier
synthetic maximum of 19.32 ms. These timers still do not include every main-thread
review/read or reload call. They do not establish a new capacity limit or a
responsiveness guarantee. The prior five-process synthetic benchmark remains
separate evidence, with its original limitations.

## Findings and interpretation

1. Native typed path Undo/Redo normalized all 12 unnamed nodes in the touched
   path from `name:null` to `name:""`. Geometry and path hashes matched exactly.
   Record this as metadata round-trip drift; do not claim byte-exact native Undo.
   This test does not isolate whether the adapter or Glyphs owns that behavior.
2. Canonical `skills/glyphs-mcp-outlines-docs/references/path-editing.md:99` still
   says scoped scripts remain available. That contradicts the current one-route
   contract and survived the previous wording pass. It remains unfixed here.
3. Real saved-file restoration works for the checked content in both formats.
   It remains a whole-document reload, not selective Undo. Small typed edits
   still benefit from their existing algorithms and selective recovery.
4. The six findings in the [previous review](../simple-native-scripting-20260926/REVIEW.md)
   remain open. Passing these happy-path tasks does not resolve Keep-to-next-task
   transitions, background eligibility, polling output or repeated hashing.
5. Successful source/CLI checks cannot qualify the installed candidate. The
   running bridge and sidecar hashes differ from the built candidate, as recorded
   in the evidence. Actual candidate editor restoration and installed chat
   scripting remain the outstanding integration gate.

Test-driver corrections are not product defects: an initial manual test edit
needed explicit Undo grouping in the standalone harness, and raw native kerning
IDs change on reload, so the oracle was corrected to compare resolved identities.
The corrected tests passed in fresh processes. Two early read requests also used
the wrong glyph selector field; they were corrected to `id` without mutation.

No product fix, runtime installation, restart, commit or publication was performed.
The saved fixture and diagnostics remain under ignored `build/`; reports contain
bounded evidence, not a copy of the full font source.
