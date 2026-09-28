# Beta 8 milestone 7 — Consolidated code and current guidance

Completed locally September 28, 2026. Stop here; milestone 8 kerning has not
started. This is an unsigned development qualification, not release publication.

The current twelve-tool contract is in
[command-set.mdx](../../content/reference/command-set.mdx). Contributor guidance,
component READMEs and the skill policy link there. The shared conversation,
scripting and checkpoint references remain the detailed agent contracts.

What changed:

- Shortened repeated tool descriptions, especially bounded reads and the
  low-level job entry. Kept exact targeting, capability gates, live paging limits,
  separate save authorization, optional source inspection, preview authorization,
  idempotency, result actions and whole-font versus selective recovery.
- Corrected the stale seven-tool/no-Python claims and source-line budgets in
  `CODEX.md`, and the bridge README's incorrect assertion that it never saves.
  Marked the v1 roadmap, initial benefit queue, reset plan and original conversation
  plan as historical; distinguished the old desktop milestone-7 worklog from this
  milestone. Historical measurements and decisions remain intact below their labels.
- Replaced arbitrary aggregate/per-module line-count assertions with import
  boundary checks. The existing deterministic build, legacy-runtime exclusion,
  exact interface, recovery and request-limit tests remain. Package checking now
  compares actual tool names with the protocol contract, catching renamed or
  duplicated declarations even when twelve decorators remain.
- Export preparation and publication now share one streaming file hash function
  in the existing file/source utility module. Both retain the same one-MiB reads,
  exact digest format and propagated IO errors. No new helper framework or module.
- Updated canonical routing guidance and synchronized its managed package mirror.
  Preserved the development SDK/scaffolder, typed algorithms, selective recovery,
  bounded reads and external analysis/export.

No execution branch, recovery system, public tool or capacity limit was added
or removed. The major shared preparation extraction was already done in milestone
2. A broader lifecycle or native-adapter refactor had no demonstrated benefit for
this milestone and was left alone.

Measured catalog size:

| Measure | Before | After |
| --- | ---: | ---: |
| UTF-8 bytes in all twelve descriptions | 17,401 | 12,962 |
| Public tools | 12 | 12 |

This removes 4,439 description bytes, **25.51%**. Measurements use real FastMCP
`tools/list` output from the pre-change and final source servers. Input schemas,
names, titles, annotations and metadata are exactly unchanged. The fresh installed
connection returns the same final catalog. Evidence: [measurement](catalog-measurement.json),
[before](catalog-before.json), [after](catalog-after.json),
[installed](installed-catalog.json).

This measures catalog overhead, not tokens, model routing accuracy, font-edit
speed or UI responsiveness. The nine routing fixtures validate representative
requests against tool schemas and job validators, and check discoverable routing
terms. They are deterministic contract tests, not a new LLM evaluation. Existing
clients may retain an older catalog until they reconnect or refresh tool discovery.

Verification:

- Tests first: [six expected failures](tests-first.txt) before consolidation;
  [three additional expected failures](package-tests-first.txt) for the historical
  benefit guidance and exact-name packaging check before those changes.
- [Final full suite](python-qualified.txt): **2,414 passed, 3 skipped, 5 warnings**.
  Covers protocol, bridge, sidecar, conversation cards/text, authorization,
  retained typed recovery, native scripts, routing, export and packaging.
  The initial focused pass exposed a missing explicit master-axis budget phrase;
  it was restored before qualification. [Focused checks](focused.txt) and
  [final consolidation/package checks](consolidation-final.txt) pass.
- Skill synchronization passes for eleven managed skills; package checks pass
  for twelve tools and both runtime architectures. The checked-out v1 provenance
  file and all 57 v1 guide files match [their initial hashes](v1-before.json).
  This preserves preexisting v1 edits/removals rather than resetting to HEAD.
  Local routing overrides and `.codex-local/` remain untracked/unstaged and outside
  distribution. No installed plugin cache was edited.
- Rebuilt the exact established `build/simple-native-scripting` target, plus a
  fresh desktop app using the normal builder. Installed only the MCP component
  and the matching desktop app under the existing authorization. The first
  installer attempt correctly refused open Glyphs; the retry followed a clean,
  authorized shutdown. All five original documents were reopened without saving;
  Dactylotype remains clean and current. Companion identities, port and startup
  setting match the previous receipt.
- Through the installed Codex connection, prepared and structurally verified a
  419-glyph OTF from the disposable `.glyphs` fixture, then accepted it into a new
  ignored local test directory. This exercised both consumers of the shared hash
  function. Independent byte hashing matches the 52,668-byte artifact manifest;
  the source hash remains unchanged. [Export evidence](installed-export.json).
  This local test artifact is not a product/font release or remote publication.
- The installed desktop app relaunched with its existing project selection and
  settings. Its verified receipt matches source and the copied app. Swift source
  was unchanged in this milestone; the 214-test milestone-6 desktop run remains
  prior evidence, not a newly repeated run. No font-edit timing matrix was repeated
  because no editing/preparation/recovery algorithm changed.

Identity evidence:

| Component | Built, installed and loaded identity |
| --- | --- |
| Sidecar | `sha256:bb5297f858c9b66a541d159c2554cafb98c1dff1c92199e56bad09b7883722df` |
| Bridge, unchanged | `sha256:c35ab0983487fb32734006b1244a83d00264f0af24ae5b7395ec77653174364c` |
| Release metadata | `2.0.0-beta.8`, desktop build `50`, Glyphs `4.1 (4107)` |

See [build manifest](build-manifest.json), [installed runtime](installed-runtime.json),
[desktop build receipt](qualified-build-receipt.json),
[installed app verification](verified-installed-app.json) and
[final state](finish-state.json). The final state has zero active jobs/bridge
operations and five clean documents. Native status is initialization-time identity
evidence plus observed behavior, not a memory attestation.

Remaining costs and qualification gaps:

- The catalog still has 12,962 description bytes because capability/scope and
  authorization boundaries must remain discoverable. Focused references load on
  demand. No claim is made that shorter descriptions alone reduce end-to-end latency.
- Complex typed preparation still copies saved sources and launches external
  workers. Checkpoint Git work and authoritative source verification retain the
  costs documented in milestone 6. Capacity and synchronous native-call limits
  are unchanged; there is no new performance or responsiveness guarantee.
- Milestone 5's actual visual Codex-card test remains incomplete because automated
  access to the Codex UI is blocked. MCP tool execution and simulated card tests
  do not substitute for that gate.
- Beta 7's final signed-update/component-migration trial remains unperformed.
  Beta 8 is not signed, notarized or published by this milestone. Earlier native
  Undo null-to-empty node-name normalization remains a separate follow-up.
- Milestone 6's documented crash/disk-full and external-effect recovery boundaries
  are unchanged; this cleanup does not qualify additional failure guarantees.

No implementation commit, staging, publication or unrelated cleanup was performed.
