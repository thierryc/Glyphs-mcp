# Beta 1 gap fixes — sequential implementation plan

**Plan only. Begin with the six high-priority fixes, one at a time.** Each fix
must pass its own tests before the next starts. After a pass, report the result
and explain the next fix with one example and its benefit. A failed or blocked
gate is not a pass; finish that correction before advancing.

Source: [v1 → v2 feature audit](../v1-v2-feature-audit-20260914/report.md).
Work in `build/milestone7/desktop`, preserving unrelated work, v1 and historical
measurements. Keep seven MCP tools, current selection node details, five existing
jobs and native Undo/discard. No new document model, history system, service,
watcher, full-font snapshot or earlier-private-build fallback.

## High-priority sequence

| Step | Fix | Example | Benefit | Required pass |
|---|---|---|---|---|
| H1 | Retire incompatible installed skill instructions | “Audit an icon font” must not invoke retired typed-v2 tools. | The agent selects a valid current workflow or states the unsupported scope accurately. | Installer ownership, backup, conflict and routing tests; actual installed skill inventory. |
| H2 | Correct migration and release documentation | “Which version and interface are installed?” gets one consistent answer. | Users can install and troubleshoot the intended Beta 1. | Identity/inventory/feed claims agree with source and qualified artifacts; links and documentation checks pass. |
| H3 | Expose compact current context and Font View selection | “Which glyphs and master have I selected?” | Routine selected-glyph work needs no script or guessed target. | Exact native agreement in Font View/Edit View, empty/multiple selections and multiple documents. |
| H4 | Discover glyph names in bounded pages | “What glyphs does this font contain?” | The agent can discover targets before reading their properties. | Exact complete inventory across pages, honest truncation, bounded work and stale-page handling. |
| H5 | Discover an explicit glyph's layers | “Show every layer of a, including intermediate and backup layers.” | Exact layer targeting without guessing IDs. | Native IDs/order/associations and available classification evidence match the fixture. |
| H6 | Discover kerning groups and stored pairs | “Which groups contain A and V, and which stored pairs use them?” | Kerning inspection works without guessed keys or an edit-preparation job. | Exact groups/keys/pairs, absent versus zero, fractions, directions, bounded pages and native timing. |

### H1 — skill cleanup

Use the existing `AgentSkillBundleInstaller` and ownership/backup logic in
`macos-installer/GlyphsMCPInstaller/Core/ConfigPatchers.swift`. Extend its existing
retirement path only as necessary; do not build a second skill-management system.

The audit identified seven installed incompatible families: icon-font, LitSquare
metadata, color-font, variable-font, production-audit, Unicode semantics and
export validation. Match the exact incompatible private instructions and verified
ownership, not a name alone: matching v1 skills must remain available for v1.

- Archive unchanged installer-owned obsolete instructions outside skill discovery,
  through existing backups. Preserve the exact prior files and a clear receipt.
- Preserve user-modified or unowned entries. Report exact paths and the existing
  explicit replacement/removal action; do not count a remaining conflict as fixed.
- Do not silently change plugin caches, source worktrees or unrelated skills.
- Keep the current entry compact. Current native coding is a separate documented
  route; unsupported specialized scope must not trigger an invented MCP command
  or a false claim that the current runtime is outdated.

Test owned retirement, current/no-op installation, user edits, unowned folders,
exact backups, restoration after failure and a second no-op run. Test ordinary
font work, native coding, specialized unsupported requests and a separate v1
connection. The current eleven-skill payload must remain synchronized. Verify
the configured installation after updating skills; no bridge reinstall or Glyphs
restart is needed for a skill-only change. Report any client refresh needed to
stop using previously loaded instructions rather than promising hot refresh.

**On pass:** “The stale routes are resolved. Next: correct the version and
migration guide so setup instructions match the candidate.”

### H2 — documentation consistency

Correct the stale bridge/protocol `0.1.0`, ten-skill count, signed-candidate
claim and stable-branch appcast guidance found by the audit. Use the existing
release-identity helper, skills manifest, build/signing receipts and beta launch
policy. Do not change independent companion versions or rewrite historical
reports by globally replacing version strings.

Update current migration, release and setup pages and synchronize managed copies
through the existing mechanisms. State what is supported, native-only or
explicitly deferred. Distinguish current source, installed components and a signed
distributable; a source label alone establishes none of the latter two.

Run the focused identity, package, routing/documentation and link checks. Build
the documentation where affected. No runtime installation or release publication.

**On pass:** “Setup information now agrees. Next: let the agent read the current
master and selected glyphs directly.”

### H3 — compact context

Add a bounded document-scoped context projection to `read_entities`. Keep the
existing `selection` node/count response unchanged. The new context describes
the native view, selected master and selected glyphs; it must distinguish Font
View, Edit View, empty selection and unavailable native evidence.

Use a native current-document marker in `list_documents` to resolve an explicit
“current font” request. A retained document ID continues to target that document
when the foreground changes. A context read must never silently retarget it.
Unavailable active-document evidence must remain unavailable, not guessed.

Start with a maximum of 100 returned selected glyphs and explicit total/returned/
complete information. Use native counts when available; do not traverse an
unbounded selection just to manufacture an exact total. Mark unavailable totals
and incomplete evidence explicitly, and require a narrower scope before an edit
based on a truncated selection. No selected-glyph pagination framework unless
native evidence demonstrates a need. Detailed nodes remain limited to one active
Edit View layer, using the existing 64-default/256-maximum policy.

First verify actual native collection/ordering semantics in a disposable fixture.
Then implement through existing read hooks, advertise the new read capability
and update the focused selection/targeting guidance and packaged mirrors. Do not
claim the old `selection.context.v1` flag alone advertises the new projection.

Test three masters, multiple selected glyphs, repeated glyph occurrences, empty
selection, Font View/Edit View, mixed native objects, two open disposable fonts,
foreground switching, dirty state, close/reopen and invalid/bounded inputs.
Existing node-detail and document-ID tests must still pass exactly.

**On pass:** “Selection and targeting match Glyphs. Next: discover glyph names
without requiring a script or loading full outlines.”

### H4 — glyph discovery

Add a glyph-collection selector to the existing read tool. Return requested
compact fields, initially names, with a page limit of 1–100 and default 100.
Reuse the small native master-page pattern where it fits; retain native order
and an opaque cursor scoped to the document. Do not copy or sort the entire
font, cache font contents or revisit all earlier glyphs for each later page.

Return total/returned/complete and a next cursor where native counts allow it.
Page reads are fresh, not a cross-call atomic snapshot. Detect the documented
stale conditions without a full-font hash; after observed edits, discard the
partial inventory and restart. Never report incomplete or inconsistent coverage
as a complete font inventory.

Test empty, one-glyph, exactly-100 and over-100 fonts plus the realistic fixture;
native ordering, missing/unsupported fields, invalid limits, glyph rename/add/
delete between pages, dirty documents and stale document IDs. Instrument visited
objects so a small response cannot hide an unbounded native traversal.

**On pass:** “Glyph discovery is exact and bounded. Next: discover each glyph's
real layer IDs, including special and backup layers.”

### H5 — layer discovery

Add a layer-collection selector scoped to one named glyph. Return exact native
ID, name, associated master ID and requested native classification evidence.
Use a 1–100 page bound, following the existing page pattern. Ordinary master,
intermediate/alternate and backup cases need native proof. Report unknown or
ambiguous classification rather than inventing special-layer grouping rules.

Keep geometry out of this inventory; detailed geometry is a later fix. Existing
explicit layer reads retain their exact-ID semantics and must accept every
discoverable supported ID without a name alias.

Test a three-master fixture with intermediate, alternate and incompatible backup
layers, duplicate names, many layers and native layer changes between pages.
Verify round trips from discovered IDs to explicit reads, preservation of layer
objects/data, dirty documents, missing glyphs and unrelated-document isolation.

**On pass:** “Layer targeting no longer needs guessed IDs. Next: make stored
kerning groups and pairs discoverable without starting a job.”

### H6 — kerning discovery

First add explicitly requested native group/key fields for named glyphs. Keep
names, stored keys and direction semantics distinct. Then add bounded stored-pair
inspection for one exact master and direction, with optional explicit key filters.
Do not compute a new effective-kerning engine or prepare collision corrections
to answer an inspection request.

Use the native lookup for each returned glyph ID; do not build a font-wide ID
map. Preserve exact raw keys and report unresolved identifiers. Target a maximum
of 100 returned pairs per page. Prototype native enumeration first and bound
work as well as output, including skipped groups; later pages must not rescan the
whole table. If exact total counts require a whole-table walk, return an explicit
unavailable total plus reliable page completeness instead. If this cannot meet
the native budget simply, the pair-enumeration portion remains blocked/deferred
with evidence; the group-read result alone must not be called full H6 completion.

Test named glyphs and groups, empty groups/tables, stored zero, absent pairs,
fractional values, LTR/RTL/vertical domains, key filters, missing targets, edits
between pages and page boundaries. Compare discovered entries with existing
exact-value reads and an independent native oracle. Dirty inspection must need
neither Save nor a job. No kerning value or group assignment may change.

**On pass:** “The high-priority gaps are closed. Next: add the missing master
metrics and axis values as requested read fields.”

## Test and delivery rule for every step

1. Freeze the relevant source, configured skills and running identities before
   changing anything. Preserve unrelated work. Write the exact expected behavior
   and failure cases before implementation.
2. Run focused unit/routing/installer tests, then the relevant lean regression
   checks. Verify skill mirrors, capability/schema agreement, unchanged seven-tool
   catalog and whitespace. A test double is not native acceptance.
3. For native read changes, build a separately fingerprinted candidate, install
   through the existing authorized installer and verify loaded bridge/sidecar and
   configured skills against its manifest. Install only changed components;
   document-only changes need no runtime reinstall. Preserve user documents and
   use fresh disposable copies of the existing fixtures/open-source Roboto Slab.
4. Verify exact results, explicit completeness, stale-target rejection and no
   implicit saves. Verify reads preserve native objects/font data and leave
   unrelated documents unchanged. Keep job/Undo/discard regression behavior.
5. Measure first attempt, one warm-up and five timed repetitions for representative
   small and paged/batch reads. Separate discovery from known-ID cost; record tool
   calls, retries and payload estimates using the existing `o200k_base` method.
   Report native callback timing separately from HTTP latency, host load and
   sample counts. Use the existing native p95 < 50 ms / maximum < 200 ms targets;
   inspect scheduling for two seconds after relevant UI/fixture changes. HTTP
   tails alone do not justify a cache, watcher or new service. A failed or missing
   required native gate prevents advancement.
6. Save a short dated result and scoped source/evidence checkpoint. State
   **passed / failed / blocked / unverified**, what changed, its benefit and any
   remaining limit. On pass describe the next fix; on failure describe the same
   fix's correction. Do not relabel a partial result to move forward.

Response format after a completed step:

> **H3 passed:** the agent now reads the selected glyphs and master correctly in
> Font View and Edit View. Native and preservation checks passed; measured costs
> are attached. **Next: H4 glyph discovery.** Example: list the font's glyph names
> in bounded pages, so the agent can find targets without a script.

This is an example of the reporting format, not a claim that H3 has been run.

## Queue after the high-priority fixes

Continue individually in the reviewed order: master properties; missing glyph
metadata; bounded layer geometry/components; native compatibility diagnostics;
instance inspection; precise native width/sidebearing recipe; native manual
kerning recipe; stylistic-set/proofing guidance. Each receives its own exact
contract, tests and installed/native qualification where applicable.

Compatibility normalize/reorder integration is a separate qualification decision;
the outer-worktree implementation must not overwrite newer bridge or Undo work.
The larger deferred features remain deferred: Unicode allocator, Designspace/UFO
exporter, numerical cross-master curve reports, automatic collision discovery,
managed annotations and persistent spacing-rule migration. Do not revive the
explicitly excluded v1 engines, live-Python MCP endpoints or custom history.

No code, skill retirement, installation or publication is performed by this plan.
