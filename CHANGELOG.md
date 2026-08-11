# Changelog

## 1.8.0 — Lean catalog and adaptive curve review

_August 10, 2026_

Glyphs MCP 1.8.0 replaces the former profile-filtered registry with one
catalog-driven MCP surface and extends the clean-room cubic engine with bounded
adaptive diagnostics. Installer build 23 supports Glyphs 3.5 and Glyphs 4.

### Lean, understandable discovery

- `TOOL_CATALOG` is now the production source of truth for every active and
  removed command: name, title, concise description, category/tags,
  model/app visibility, effect, lifecycle/replacement, output schema, and all
  four MCP safety hints.
- One registration helper applies catalog metadata to FastMCP. Startup and
  tests fail on a missing catalog entry, duplicate registration, invalid
  schema, or attempted registration of a removed command.
- The raw registry contains 76 active tools. MCP Apps metadata exposes 65 to
  the model and reserves 11 feedback or host-UI wrappers for the app. Generated
  metadata for the model surface stays below 160 KiB.
- Eight commands are removed without aliases: `render_glyph_review_image`,
  `docs_enable_page_resources`, `measure_stem_ratio`,
  `review_collinear_handles`, both direct italic review/apply commands, and
  both direct compensated-tuning review/apply commands. Catalog tombstones
  document their replacements without registering them.
- The old profile selector, saved profile preference, startup filtering,
  aliases, and profile module are removed. Existing saved values are ignored.

### Structured workflow results

- All candidate-session tools, curve geometry/Reporter controls, four spacing
  tools, and kerning read/set/review/apply tools now return an additive
  `resultSchemaVersion: 1` structured envelope.
- The envelope normalizes mode, status, targets, summaries, warnings, errors,
  and workflow-specific data. Exact legacy JSON text remains available for
  existing clients.
- The existing MCP Apps feedback contract remains compatible while its
  visibility, annotations, descriptions, and schema attachment move into the
  catalog.

### Adaptive curve quality

- `review_curve_quality` defaults to `analysis_mode="adaptive"` and returns
  `geometryDataVersion: 2`. `sampled_v1` preserves reproducible 1.7 sampling.
- Bounded analysis adds parameterized extrema, inflections, stationary points
  and cusps, adaptive arc length, turning angle, self-intersections, G0/G1/G2
  joins, curve-to-line continuity, and declared-versus-geometric smoothness.
- Stable analytic roots are used where appropriate; bounded de Casteljau root
  isolation/subdivision and arc-length-aware sampling handle the remaining
  cases. Results remain measurements and conservative warnings, never an
  artistic score.
- `review_curve_quality_across_masters` compares compatible explicit masters
  and reports Tunni-ratio drift, normalized-curvature variation, event-count
  changes, continuity variation, path/shape indices, and stable topology
  incompatibility reasons.
- The native curve Reporter accepts `curvature`, `curve_events`, or both.
  Extrema, inflections, cusps, and continuity warnings are drawn with bounded
  markers; candidate and curve Reporters stay independent.

### Skills, tests, and compatibility

- Italic and outline guidance now routes batch work through candidate preview,
  session review, dry-run acceptance, explicit approval, and confirmed
  acceptance. Removed, app-only, misspelled, or unsafe routing references fail
  deterministic skill tests.
- The command table and count/category summaries are generated from the
  catalog; README keeps only the concise overview and link.
- Undefined Glyphs 4 master metrics now serialize as JSON `null` instead of
  leaking the Objective-C `2^63` sentinel value.
- Explicit kerning exceptions now resolve public glyph names to Glyphs' native
  glyph-ID keys in both host versions, while preserving `@MMK_*` class keys.
  This prevents shadow name-key pairs from being created in Glyphs 3.5.
- Analytic, metamorphic, adversarial, cross-master, Reporter, response-bound,
  registration, structured-result, and deterministic routing fixtures extend
  the suite. The combined Python feature suite passes 737 tests with 4
  intentional environment-dependent skips before final release gates.
- Mathematics remains standard-library based, local, deterministic, and
  clean-room with no ML, cloud service, native binary, or new dependency.

## 1.7.0 — Cleanroom cubic curve geometry

_August 10, 2026_

Glyphs MCP 1.7.0 adds independently implemented cubic Bezier review and
guarded handle balancing for Glyphs 3.5 and Glyphs 4. It introduces no model,
network service, native binary, or additional dependency.

Installer build 22 extends the same 1.7.0 candidate with a hybrid native
candidate-review workflow and grid-safe Tunni proposals. It supersedes and
invalidates every build-21 live QA result for final acceptance.

### Hybrid candidate review

- A second Reporter adds **View > Show Glyphs MCP Candidate**. It leaves the
  normal Glyphs outline unobscured and draws only the source/candidate
  symmetric difference: warm golden yellow for a current proposal and coral
  red with a `STALE` legend after a source edit. Candidate curvature remains a
  separate Reporter so visual decisions are not buried in overlay noise.
- The difference compositor now builds AppKit-native, topology-paired contour
  ribbons by tracing each source contour and its candidate in reverse and
  filling one `NSBezierPath`, following Glyphs' documented Reporter drawing
  pattern. Live Glyphs 4 inspection found that XOR, nested-clear groups, and a
  direct CoreGraphics fill could report successful drawing while emitting no
  visible pixels. The blend-free path retains `0.82` overlay alpha, changes no
  destination pixels outside the paired ribbons, and fails closed before
  drawing when display topology is incompatible.
- Typed preview tools cover Tunni balancing, collinear smoothing, italic first
  pass, and compensated tuning. They create bounded detached sessions and
  automatically enable the Reporter without dirtying or saving the font.
- Shared tools inspect/toggle sessions, optionally materialize complete native
  layer copies for normal Glyphs editing, re-review bounded manual deltas,
  accept a short-lived fingerprint-bound state, or discard only session-owned
  layers. Materialized manifests survive plug-in restart; ephemeral previews do
  not.
- Manual promotion is operation-specific. Topology, path/shape order,
  component identities and smart values, protected hints/guides/annotations,
  and unrelated metadata remain blocked. Successful acceptance removes
  candidate layers only after exact verification and preserves existing italic
  and compensated-tuning backup behavior.
- Rollback now repairs a Glyphs 4 identity edge case: reattaching a candidate
  layer can assign it a new layer ID. The layer metadata, process-local
  session, and persisted manifest are remapped together before rollback is
  reported successful, so a recovered candidate never points at a stale ID.
- Sessions are capped at 16 sessions, 256 entries, and 100,000 nodes. Oversized
  requests fail instead of truncating. Preview/review tools are Read-only;
  materialize/accept/discard remain Edit-only. No custom SelectTool is added.

### Grid-safe Tunni

- `review_tunni_geometry`, `apply_tunni_balance`, and candidate preview now
  default to `grid_policy="font"` using the ready-calculated
  `font.gridLength`; `continuous` remains explicit opt-in.
- `idealProposed` preserves continuous arithmetic. The authoritative
  `proposed` result comes from a deterministic bounded lattice search guarded
  by ray direction, movement, imbalance, on-grid, and `0.25` degree tangent
  limits. Integral grids return JSON integer coordinates and impossible cases
  return `no_safe_grid_candidate`.

### Curve engineering tools

- `review_tunni_geometry` reports intersections, endpoint handle ratios,
  relative imbalance, eligibility reasons, and conservative balance proposals
  for one explicit glyph/master/path target.
- `apply_tunni_balance` accepts only explicit curve end-node indices and
  requires exactly one of dry run or confirmation. Confirmed changes run on the
  main thread; target resolution, snapshot, recomputation, eligibility, writes,
  and read-back share one transaction. It requires a callable layer change
  batch, returns actual verified before/after coordinates, rolls back the
  complete path coordinate snapshot on failure, and never saves the font.
- `review_curve_quality` returns bounded sampled signed curvature, normalized
  metrics, inflection sign changes, degenerate tangents, exact maximum/median
  spike warnings with JSON-safe infinite-ratio markers, and smooth-join
  discontinuity warnings without claiming artistic approval.
- `render_glyph_review_image` accepts a `curvature` overlay with signed comb
  colors, a returned teal-positive/pink-negative sign legend, UPM-aware
  scaling, a `0.25em` length clamp, deterministic sampling reduction under a
  hard stroke budget, and explicit raw-path component omissions. This PNG
  curvature path is now a deprecated compatibility fallback.
- A native `GlyphsMCPCurvatureReporter` adds **View > Show Glyphs MCP
  Curvature**. It draws live signed comb teeth plus connected envelope runs in
  Edit View at `0.65` alpha. Native defaults are now 51 samples per cubic, a
  `0.010` scale, and a `0.12em` normal clamp with a `0.25em` hard guard.
  Curvature magnitude is placed along the path right normal, so correct Glyphs
  winding sends outer-contour combs outward and counter combs into counter
  space. Signed curvature still controls teal/pink colors and inflection
  behavior. Path direction participates in the bounded cache signature; the
  frame cap remains 2,000 teeth. The deprecated PNG keeps 51 samples, `0.02`,
  and `0.25em` while receiving the same outside-ink placement correction.
- `set_curve_review_overlay` toggles that Reporter through Glyphs' documented
  activation API, while `get_curve_review_overlay_state` returns availability,
  activation, last-draw counts, clamp/cap state, errors, and omitted components.
  Both tools are available in Read-only and Edit and never change or save a
  font.

### Cleanroom and compatibility boundary

- The geometry engine accepts plain node records and imports neither
  GlyphsApp nor AppKit/PyObjC. JSON review and visual rendering share the same
  formulas and fixtures.
- No SuperTool or SCGlyphsLib source is copied, translated, linked, or shipped.
  The contributor cleanroom record documents formulas, rejection limits,
  mutation safeguards, and deferred features.
- The Read-only profile exposes both review tools and both native curvature
  Reporter controls; Tunni mutation remains Edit-only. Tool schemas and path
  access cover Glyphs 3.5 paths and Glyphs 4 mixed shapes.
- Restricted profiles follow FastMCP's authoritative tool-manager registry,
  verify the exact enabled tool set before HTTP exposure, and abort startup
  rather than falling back to Edit tools when filtering cannot be proven.
- Numeric thresholds must be finite, explicit segment indices must be genuine
  integers, and the one-unit handle floor cannot be weakened by callers.
- Harmonization, callipers, path simplification, and ink coverage remain
  intentionally deferred pending separate specifications and validation.

### Server restart compatibility and verification

- A repeated Stop -> Start is refused while the prior Uvicorn thread is still
  alive. After it has fully stopped, Glyphs MCP clears the guarded
  `sse-starlette` 2.4.1 `AppStatus` shutdown flag and loop-bound event before
  constructing the HTTP app for the next server event loop. Missing or changed
  `AppStatus` layouts are tolerated without blocking startup.
- An adversarial surface contract fixes the intentional budget at `83`
  decorated tools: `81` protocol-visible and `2` app-only. It requires unique,
  bounded descriptions, preserves snake_case except for the legacy
  `ExportDesignspaceAndUFO` name, and proves the Read-only allowlist contains no
  font mutation, execution, save, or file-writing tool. The three compensated-
  tuning commands now expose concise descriptions, and packaged skills use only
  the current Read-only/Edit profile language.
- The build-22 local gate passes `723` Python tests with `4` intentional
  environment-dependent skips, all `104` Xcode installer tests, the unsigned
  Debug installer build, documentation/skill validation, source/Plugin Manager
  parity, schema/profile coverage, and release-security metadata checks. The
  corrected candidate module passes the complete HCR1-HCR8 matrix in both
  Glyphs 4 and Glyphs 3.5.
- A final Glyphs 4 restart loaded runtime `1.7.0+70b5bcb204b1`. Its
  authoritative live tool registry contained all `83` registered entries with
  zero blank descriptions, including the three compensated-tuning commands.
  The already-open Codex task retained its pre-reconnect catalog text, so
  clients still need to reconnect after a plug-in restart to refresh
  `tools/list` descriptions.
- On August 10, the corrected candidate module was reloaded from the canonical
  checkout into Glyphs 4.0 / Python 3.14.6 and exercised on a serialized
  `/private/tmp` Gee gee copy. Stale-source, topology, unrelated-node, permitted
  manual-edit, changed-after-review, and consumed-token checks all failed or
  passed as specified. Injected write, read-back, `endChanges`, and manifest
  cleanup failures each restored the source, candidate, and manifest. Glyphs 4
  assigned a new layer ID during cleanup rollback; the repaired manifest
  followed it and the session immediately re-reviewed as ready. Reloading the
  process-local state removed an ephemeral session while recovering the
  materialized one from font/layer metadata; guarded discard then removed only
  that candidate. The copy closed without save and retained its exact 412-file
  hash `64bb9cdd82049885cb04cf09646d3a94d05e464c867357d0c4a7d93cb1396c11`.
- On August 10, Glyphs 3.5 build 3530 / Python 3.12.3 loaded runtime
  `1.7.0+ef4b95f03e4d` and completed the same adversarial candidate matrix on a
  serialized 37-file SDK v3 fixture. Stale source, topology, unrelated-node,
  permitted manual-edit, changed-after-review, and consumed-token cases all
  behaved as specified. Injected write, read-back, `endChanges`, and manifest
  cleanup failures restored complete state; cleanup rollback reassigned the
  materialized layer from `0A16CF95-28A0-4F5C-90A6-3C54A2FEC703` to
  `C1A668C5-CD99-4E8E-AC0F-4B830C82469C`, and the repaired manifest followed
  that new ID. Reloading process-local state discarded an ephemeral-only
  session while recovering the materialized session from metadata; guarded
  discard removed only its owned layer. The fixture closed without save and
  retained its exact tree hash
  `b98c3e2aaa7f916a4c7fc7cc467a75a9ba1ad154f631da6ea85cc966a2284fd9`
  and font hash
  `86ba946d125a404e6bb9ccce992b832c93f81bf16edf5895969ac615acd5baa8`.
- A final restarted Glyphs 4.0 / Python 3.14.6 pass loaded runtime
  `1.7.0+dc567a3732de` and proved that the AppKit-native difference compositor
  emits real localized pixels. An overlay-off/on comparison of Gee gee `G` at
  the same 650-point viewport found 2,450 changed canvas pixels, including 511
  yellow-shifted pixels, while the Reporter reported one changed path, 12
  changed nodes, `8.27806` units maximum sampled outline displacement, and no
  drawing error. The user reviewed and explicitly approved that proposal;
  token-bound dry-run and confirmed acceptance then changed exactly the 12
  reported off-curve handles, verified the read-back, removed the ephemeral
  session, and reported `fontSaved:false`. The source document is intentionally
  left changed in memory for the user to save or discard; Glyphs MCP did not
  save it.
- Live Glyphs 4.0 with Python 3.14.6 and runtime
  `1.7.0+531bbc42f912` passed the all-master candidate preview, native
  materialization, cosmetic rename plus one permitted manual edit, bounded
  re-review, dry-run, confirmed promotion, overlay-only promotion, consumed
  token rejection, metadata recovery after process-local state loss, and
  owned-layer discard on a serialized `/private/tmp` copy of Gee gee. Five
  source masters matched their complete expected post-acceptance snapshots;
  candidate layers, manifests, backups, and ephemeral state were empty after
  cleanup. The copy was closed with changes discarded, its 412-file tree hash
  remained `a4fe531545c7ffb75fd686e94d23dbc687d1e7cd93ebc740904869ee1cbc76b2`,
  and no font was saved.
- A final restarted Glyphs 3.5 / Python 3.12.3 pass loaded runtime
  `1.7.0+dc567a3732de` and visually confirmed both native Reporters on Inter
  `G`, Regular. The candidate compositor emitted one localized golden ribbon
  group for four eligible Tunni segments; an overlay-off/on capture at the same
  650-point viewport found 19,171 changed pixels in the glyph crop, including
  1,350 clearly yellow-shifted pixels. The separate curvature Reporter drew
  408 bounded teeth across eight cubics: the teal outer comb pointed outside
  the shape and the pink inner comb pointed into the white counter, with no
  clamp, cap, degenerate sample, warning, or drawing error. Candidate review
  and acceptance dry-run passed without changing or saving the already-edited
  source document.
- That live pass found and fixed a fail-closed integer/float representation
  mismatch: the grid engine intentionally serializes integral coordinates as
  JSON integers while Glyphs reads the same `NSPoint` values back as floats.
  Review-token fingerprints remain strict; recomputation and write-back now
  compare complete snapshots geometrically. The regression covers an
  unchanged materialized candidate and rejects any real coordinate change.
- Live Glyphs 3.5 build 3530 with Python 3.12.3 and the same fixed runtime
  `1.7.0+531bbc42f912` passed a native all-master Reporter preview and a guarded
  materialize, re-review, dry-run, and confirmed acceptance on Inter glyph
  `a`. Five masters produced eligible grid-safe proposals and followed active
  master switching; the Display master was correctly excluded because its
  imbalance was already below threshold. Acceptance changed exactly the two
  targeted Thin-master handles, matched the complete expected layer snapshot,
  removed the candidate layer and manifest, and created no backup.
- The Glyphs 3.5 mutation ran only on a serialized `/private/tmp` package copy.
  It passed the fixed integer/float semantic comparison, was closed with
  changes discarded, retained its exact 3022-file tree hash
  `8da828278bf638edb0e47dfd8e6bb0ca399e30aa51f3649dffd8b3e6ba60ef58`,
  and was deleted. The user's original Inter document received read-only
  Reporter previews only; its exact source fingerprint, handles, manifest,
  and on-disk tree remained unchanged. It was already document-edited before
  QA, so it was left open and never saved by the test.
- Live Glyphs 3.5 build 3530 with Python 3.12.3 and runtime
  `1.7.0+dc6234a3dc21` passed CG1-CG6 on an untitled path-only disposable
  font. The pass verified Tunni ratios and rejection reasons, signed curvature,
  a real AppKit PNG comb, exact dry-run immutability, two-handle confirmed
  writes with stale-state recomputation, and complete rollback for controlled
  write, read-back, and `endChanges()` failures.
- Profile restarts exposed exactly `29` Read-only tools and `71` Edit tools;
  mutation and code execution were unavailable in Read-only. The active-thread
  restart guard followed its expected wait path, and a subsequent restart after
  full shutdown initialized successfully.
- The Glyphs 3.5 pass used two open cubic paths and no components. Component
  omission and mixed-shape ordering remain covered by automated tests and the
  live Glyphs 4 pass. Synthetic mixed-component and visible serialized
  temporary fixtures exposed Glyphs 3.5 host alignment and autosave hazards;
  all temporary artifacts were removed, the disposable font was closed without
  saving, and the user's remaining font stayed unedited.

## 1.6.0 — Verified update staging and safer spacing workflows

_August 6, 2026_

Glyphs MCP 1.6.0 adds opt-in, fail-closed update discovery and staging while
making automatic spacing substantially safer for capitals, figures, tabular
fonts, negative sidebearings, and low-confidence punctuation. It also refreshes
the bundled italic workflow with Unicode-aware symbol review guidance.

### Easier future updates

- Background checks use GitHub's stable latest-release metadata, derive the
  exact tag page locally, stay bounded and non-modal, and can be disabled.
- The installer offers a plain-language **Make future updates easier** option
  separately for Glyphs 3 and Glyphs 4. Opting in installs a fixed,
  Developer ID-signed helper
  with hardened runtime, timestamp, ownership, permission, team, and protocol
  checks.
- The server window presents available versions in a discreet positive banner
  with a simple message and an aligned action. Signing and verification details
  remain in the release documentation instead of the main status message.
- Release discovery never downloads or changes the installed plug-in. A user
  must click **Prepare Update** before the helper may fetch the exact versioned
  installer and checksum assets.
- Preparation verifies checksums, archive structure, version, Developer ID,
  notarization, and the staged plug-in receipt. The running and installed
  plug-ins remain untouched; 1.6.0 deliberately stages a verified candidate
  rather than silently activating it.
- Version 1.5.4 cannot bootstrap this new helper. Existing users install 1.6.0
  with its signed installer; 1.6.0 can then prepare later stable releases and
  direct the user to their signed installer for activation.
- Cancellation, offline failure, malformed metadata, hostile URLs, bad
  signatures, wrong versions, and unowned updater data fail closed without
  interrupting the MCP server.
- Automatic client reconnection no longer leaves the server window showing a
  false red HTTP 404 when a pre-restart session is rejected and cleaned up.
  Expected transport retries remain available in the debug log, while genuine
  MCP request failures still appear in the activity status.

### Class-aware spacing safeguards

- Automatic references now resolve by glyph class: uppercase letters use `H`,
  lowercase letters use the lowercase strategy, and decimal figures use `one`.
  Explicit `x`, `H`, `one`, `*`, and arbitrary available glyph references keep
  their prior meaning.
- Review and apply results report glyph classification, requested and resolved
  references, deterministic fallbacks, current/proposed metrics, normalized
  changes, confidence, tabular evidence, and structured issues.
- Optional em-normalized guards warn below `-0.05em` and block ordinary upright
  base glyphs below `-0.10em` by default. Geometry-supported overhangs, marks,
  italics, allow lists, and named user overrides remain explicit and auditable;
  negative values are never silently changed to zero.
- Mutating apply refuses blocked or manual-review results unless the glyph is
  named in the matching override list. Review and dry-run apply share the same
  assessments, and no spacing operation saves a document automatically.
- Automatic tabular preservation now requires fixed-pitch metadata, equal
  default-figure widths, metrics relationships, or explicit mode. Narrow
  punctuation is treated as lower-confidence visual-review work.

### Optional multi-host agent plugins

- One shared versioned package now provides native manifests and repository
  marketplace catalogs for Codex/ChatGPT, Claude Code, Cursor, and GitHub
  Copilot CLI.
- Every host manifest is aligned to Glyphs MCP `1.6.0` and loads the same nine
  packaged skills and localhost MCP connection. Skills inherit the package
  version, while the server continues to report the native plug-in version.
- Agent plugins remain host-owned and optional. The native installers do not
  add or remove them, and repo-local skills, global standalone skills, and
  manual MCP configuration remain supported.
- GitHub Copilot CLI supports both the repository marketplace and direct
  subdirectory installation. The repository does not opt Copilot cloud agents
  in automatically through `.github/copilot/settings.json`.

### Bundled skills and guidance

- New `glyphs-mcp-release` skill separates local candidate preparation, signed
  artifact production, verified upload, and public publication, with linked
  commands and explicit authorization gates for every external release action.
- `glyphs-mcp-spacing` now documents the complete guarded review, comparison,
  proofing, dry-run, override, verification, and no-save workflow, with a linked
  negative-sidebearing reference.
- `glyphs-mcp-italic-first-pass` now surfaces Unicode-aware review tiers for
  symbols that may remain upright. These tiers are advisories only and never
  silently exclude or transform glyphs.
- Canonical skills, the shared multi-host package, runtime mirrors, prompts,
  documentation, and release-gate coverage are synchronized.
- The release-version helper updates all four agent-plugin manifests and
  supports a non-mutating dry run while retaining support for current generic
  server-version wording and older FastMCP-specific README wording.
- Multi-word documentation searches fall back to ranked individual terms only
  when the complete phrase has no match, so class-and-member queries such as
  `GSLayer bounds` resolve to the bundled API reference.

## 1.5.4 — Installer ABI diagnostics

_July 31, 2026_

Glyphs MCP 1.5.4 prevents both supported installers from reporting success when
Glyphs' active Python cannot import existing native dependencies. It addresses
the Python 3.14 / `cpython-311` failure reported in issue #47 without changing
or removing shared packages.

### Detection before changes

- Both installers run the same pure-standard-library JSON probe with the exact
  Python selected for each Glyphs 3 or Glyphs 4 target.
- The target's `Scripts/site-packages` is explicitly prioritized while checking
  the complete runtime import set, including `pydantic_core`, `objc`,
  `_cffi_backend`, and `rpds`.
- Missing packages and pure-Python modules remain non-blocking before
  dependency installation. Existing broken imports, incompatible CPython tags,
  and incompatible Mach-O architectures block installation.
- Compatible CPython extensions, `.abi3` modules, universal binaries, and mixed
  directories with a successfully imported compatible candidate are accepted.
- Every selected target passes preflight before pip, plug-in replacement, or
  client configuration starts. Errors identify the interpreter and offending
  files and remain available as structured JSON in the log.

### Strict verification, limited scope

- Post-install verification now uses the shared probe instead of duplicated
  inline import snippets. Missing imports, nonzero exits, malformed output,
  unexpected origins, timeouts, and stderr-only failures prevent completion.
- Interactive and non-interactive terminal installs use the same checks and
  retain exit code `2` for incompatible or unverifiable runtimes.
- This release does not delete, back up, reinstall, or isolate shared packages.
  Dependency isolation and automated repair remain a later milestone pending
  feedback from the Glyphs team.
- Signed-bundle bytecode-cache handling remains a separate packaging task and
  is not changed by this diagnostic patch.

## 1.5.3 — Verified server readiness and startup diagnostics

_July 29, 2026_

Glyphs MCP 1.5.3 closes the diagnostic gap where a live server thread could be
reported as running before Uvicorn had completed startup and bound its socket.

### Server readiness

- The server panel stays in **Starting** until pinned Uvicorn 0.35 confirms
  readiness; only then does it report **Running** or emit success output.
- Server-thread exceptions and exits are classified as startup failures,
  unexpected exits, or intentional stops.
- Failures persist as a red **Error** with the affected port and retry
  guidance. Full diagnostics go through `GeneralPlugin.logError` to Glyphs’
  Macro Panel, with `print` as a fallback.
- Manual startup failures retain the alert, while auto-start failures remain
  non-modal. Recovery stays user-controlled with no automatic retry loop.
- The localhost endpoint and MCP protocol are unchanged.

## 1.5.2 — Ownership-safe skills and atomic parameter edits

_July 29, 2026_

Glyphs MCP 1.5.2 closes two safety gaps found in the 1.4.0 review while
preserving the signed 1.5 release path and deterministic Balanced workflow.

### Safety fixes

- Global Codex and Claude Code skill installs now write a repository-owned
  marker into every copied skill directory.
- Skill overwrite and uninstall operations require that exact marker and skill
  name. An unrelated or older unmarked same-name directory is preserved and
  reported instead of being removed.
- Confirmed `set_custom_parameters` batches now snapshot each targeted
  parameter's existence, exact value, and active state before mutation.
- Every assignment and deletion is verified. A failed write, read-back, or
  redraw restores and verifies the complete batch and reports structured
  rollback status without saving the font.

### Upgrade note

Skill directories installed before ownership markers were introduced are
deliberately treated as unverified. Move or remove a confirmed older Glyphs MCP
skill directory once before reinstalling; the new installation will carry the
marker used by future updates and uninstall operations.

## 1.5.1 — Signed release provenance and corrected plug-in delivery

_July 29, 2026_

Glyphs MCP 1.5.1 republishes the 1.5 feature line from a GPG-signed annotated
tag and carries the deterministic Balanced workflow through the hardened
release path introduced in 1.5.0.

### Release integrity

- The exact `.glyphsPlugin` payload is signed with Developer ID, submitted to
  Apple independently, stapled, and then stored unchanged in the notarized
  installer.
- macOS-app and terminal Copy installations preserve the payload bytes, CDHash,
  and Team ID. Any mismatch fails transactionally instead of ad-hoc re-signing
  the installed plug-in.
- The installer app, DMGs, checksum manifest, embedded payload, and a simulated
  installed copy must all pass signature, timestamp, notarization, Gatekeeper,
  version, and checksum gates before publication.
- The source release is identified by a GPG-signed Git tag registered to
  Thierry Charbonnel's verified GitHub email. This Git signature is separate
  from Apple Developer ID signing and notarization.

### Confirmed 1.4.1 issue

The final plug-in installed by 1.4.1 can carry an ad-hoc signature, no Developer
Team ID, and a quarantine attribute. macOS may consequently block it when
Glyphs starts even though the outer installer was notarized. Users should
upgrade through the signed installer and should not bypass Gatekeeper or remove
quarantine manually.

The experimental Balanced italicification behavior and compatibility defaults
remain those documented for 1.5.0.

## 1.5.0 — Experimental italic first passes for design exploration

_July 29, 2026_

Glyphs MCP 1.5.0 introduces Balanced italicification as an opt-in candidate
inside an explicitly experimental first-pass workflow. Its purpose is to help
a designer construct a useful emphasis companion to a Roman—not to generate
or replace a finished italic design. The expanded validation ranks Balanced
best for deterministic path geometry and promotes it as the recommended
experimental mode. Existing calls still default to Cursivy.

### The highlights

- **A reproducible mechanical starting point.** Balanced no longer depends on
  the installed Glyphs Transformations filter. It builds Raw, applies the
  pure-Python conservative correction at partial strength, interpolates those
  coordinates, then applies the requested final straight-stem compensation
  without changing topology or curve handles.
- **Design work remains visible.** Review reports anchors, components, bounds,
  metrics, topology, stem measurements, filter failures, and blocked component
  masters before any confirmed apply. Optical form, rhythm, spacing, kerning,
  alternates, and proofing remain manual design decisions.
- **Three-family Broad-Latin evidence.** A fixed 543-glyph manifest covers
  Basic Latin, Latin-1, Latin Extended, punctuation, currency, letterlike
  symbols, and number forms in pinned Inter and Noto Sans sources; pinned IBM
  Plex Sans contributes 391 Roman/Italic shared values.
- **Balanced passes the promotion gates.** All 543 Inter, 543 Noto Sans, and
  391 Plex glyphs preserved topology and source data. The test accepted 135,
  102, and 102 stem pairs respectively, with effectively zero source-width
  error after compensation. Recursive construction analysis identified and
  blocked 23 Inter and 2 Noto Sans glyphs whose component transforms do not
  commute with local shear, including Inter's reflected `d` and `q`. No unsafe
  component construction was applied.
- **High-resolution visual evidence.** Paginated 144-DPI contact and
  silhouette-difference sheets compare Roman, Raw, deterministic Partial,
  deterministic Balanced, and each family's official italic. A combined
  `4800 × 6424` story sheet shows both capacity and design limits. Official
  italics remain qualitative references, not numeric targets.

### Compatibility

- Existing calls that omit `slant_mode` continue to use Cursivy.
- Balanced remains opt-in and is the recommended experimental option, with
  `curve_strength=0.75` and `stem_compensation=1.0`. The controls are
  independent; full final compensation can make the partial interpolation
  visually subtle on accepted stems.
- Review is a genuine detached-layer dry run, confirmed apply never saves the
  font, and Raw/Cursivy behavior remains compatible with previous releases.

### Installation integrity

- The macOS installer now preserves the embedded plug-in's Developer ID
  signature instead of replacing it with an ad-hoc signature. Source, staged,
  and installed bundles must have the same CDHash and Team ID, or installation
  is rolled back.
- Terminal **Copy** mode downloads the installer ZIP for the checkout's exact
  published version and verifies its SHA-256 manifest, Developer ID identity,
  notarization ticket, Gatekeeper acceptance, version, and embedded plug-in
  signature before installing it transactionally.
- The installer's update check and update payload now resolve the latest
  non-draft, non-prerelease GitHub release. Mutable `main` source archives are
  no longer used as an update channel.
- Source-link mode remains available for trusted development checkouts, but is
  explicitly outside the signed-release and notarization guarantee.
- Public release assets no longer include the unsigned standalone plug-in ZIP.
  The release verifier simulates the final installed copy and requires its
  executable bytes and Developer ID signature to remain unchanged.
- Signed plug-in and skill payloads are stored in the installer as an immutable
  compressed-tar resource. The release build verifies its checksum and every
  extracted code signature again after signing the outer app.
- The exact archived plug-in is notarized independently before the outer app,
  and its Apple ticket is stapled into the custom `.glyphsPlugin` bundle before
  the outer app is re-signed and notarized. Both installer paths validate that
  ticket before copying the plug-in.

Read the
[experimental italic guide](content/italic-first-pass.md) and the
[Broad-Latin benchmark](content/contributor/italic-balanced-broad-latin-benchmark.md).

## 1.4.1 — Faster, bounded installer dependency setup

_July 28, 2026_

**Known issue:** the final installed plug-in can be ad-hoc signed and retain a
quarantine attribute, causing macOS to block it when Glyphs starts. Upgrade to
1.5.1 or later; do not bypass Gatekeeper or remove quarantine manually.

Glyphs MCP 1.4.1 makes repeated installer runs substantially smaller and more
predictable, especially with Glyphs 4 and Python 3.14.

### The highlights

- **Only the required PyObjC bindings.** The installer now installs
  `pyobjc-core` and `pyobjc-framework-Cocoa`, which provide the Objective-C
  runtime, Foundation, and AppKit used by Glyphs MCP, instead of every macOS
  framework binding.
- **Healthy dependencies are reused.** Before invoking pip, the installer
  compares every pinned requirement and verifies the runtime imports. When the
  installed environment is current, dependency installation is skipped.
- **Bounded waits and useful failures.** Dependency commands have an overall
  timeout, while pip uses bounded network timeouts and retries. Cancellation
  terminates the running command cleanly.
- **Visible Wizard progress.** The Wizard and advanced Install view show the
  current resolution, download, installation, or verification activity instead
  of leaving package details only in the Status log.
- **Consistent helper installers.** Terminal and shell installation paths no
  longer upgrade pip or request forced package reinstalls.

### Verification

- The complete local release gate passes with `401` Python tests and `82`
  macOS installer tests, followed by a successful unsigned Debug build.
- A disposable Python 3.14 environment imports `objc`, `Foundation`, `AppKit`,
  MCP, and FastMCP with `75` installed distributions, including only `2`
  PyObjC distributions. The previous full PyObjC dependency path installed
  `232` distributions, including `159` PyObjC distributions.
- The dependency preflight recognizes the completed environment and skips pip
  on the next installer run.

## 1.4.0 — A reliable plug-in UI and portable skill workflow

_July 27, 2026_

Glyphs MCP 1.4.0 expands the repository plug-in into a consistent workflow for
ChatGPT, Codex, Claude, and Cursor. It repairs embedded feedback actions,
refreshes the UI for current ChatGPT light and dark surfaces, adds guarded
authoring tools, and grows the synchronized skill bundle to eight workflows.

### The highlights

- **Feedback actions now reach the host.** OpenType Features, Refresh, and
  reviewed actions detect the host's server-tool capability, use the compatible
  OpenAI bridge when needed, and surface recoverable failures instead of
  appearing to do nothing.
- **A ChatGPT-aligned review panel.** Updated colors, type sizes, whitespace,
  focus states, action hierarchy, and responsive layouts work across light,
  dark, and narrow embedded surfaces.
- **Eight portable skills.** The canonical skill sources and packaged plug-in
  mirrors now cover connection, spacing, kerning, OpenType features, outlines
  and documentation, italic first passes, icon-font Unicode workflows, and
  Glyphs plug-in development.
- **More guarded font operations.** New tools support previewable custom
  parameters and Unicode assignment while preserving the existing confirmation
  and no-automatic-save boundaries.
- **Cross-client setup guidance.** New documentation covers the embedded
  Codex/ChatGPT UI, Claude Code and standard Claude MCP connections, and Cursor
  through `.agents/skills`, optional `.cursor/skills`, and
  `.cursor/mcp.json`.
- **Structured and text fallbacks remain first-class.** Claude, Cursor, and
  other MCP clients can use the same tools and skills even when their host does
  not render the embedded OpenAI UI.

### Verification

- The complete Python suite, Xcode installer tests, unsigned Debug installer
  build, documentation build, source/package synchronization checks, and local
  release checks cover this release.
- Browser fixtures exercise light, dark, and narrow layouts.
- Host-bridge fixtures verify successful OpenType Features and Refresh calls as
  well as recoverable unavailable and failure states.

### Remaining live QA

Live Glyphs 3.5 and Glyphs 4 compatibility checks remain a separate manual
validation step before publishing signed and notarized installer assets. This
tag does not create a GitHub Release or publish packages.

## 1.3.0 — Glyphs 4, safely—and a better Codex workflow

_July 19, 2026_

Glyphs MCP now understands the new Glyphs 4 file-format model while continuing
to work with Glyphs 3.5. It also introduces a first-class Codex marketplace
plug-in and an embedded review panel. This release is designed around one
promise: AI-assisted font work should be powerful, visible, and safe.

### The highlights

- **A first-class Codex experience.** Install the repository marketplace
  plug-in to connect Codex to Glyphs MCP, load six focused typography skills,
  and use an embedded feedback panel without duplicating global MCP setup.
- **Review before you apply.** The new panel presents server, font, glyph, and
  OpenType reports alongside guarded spacing, kerning, and handle-smoothing
  previews. Short-lived plans are revalidated before explicit confirmation;
  none of these workflows saves the font.
- **Advanced outline data stays attached.** Path edits preserve mixed shape
  order, shape groups, locked state, styling, colors, gradients, user data,
  higher-order interpolation metadata, and properties introduced by Glyphs 4.
- **Safer path round-tripping.** `get_glyph_paths` now returns
  `pathDataVersion: 2`, including shape positions and the raw node information
  needed to distinguish newer node types. Existing version-1 payloads are still
  accepted.
- **Atomic edits with a safety net.** Compatible coordinate edits happen in
  place. Topology changes clone existing paths and nodes, retain surrounding
  components and images, and restore the original layer if writing or
  verification fails.
- **Your file format is visible—and respected.** Font summaries report
  `formatVersion` and `lastSavedAppVersion`. Saving reports the format before
  and after the operation and never requests a conversion.
- **Official Glyphs 4 documentation is built in.** Documentation search now
  includes the official ObjectWrapper reference, version 3 and 4 file-format
  specifications, and the regular `.glyphs` and `fontinfo.plist` schemas.
  Results identify their source type, format version, and official URL.
- **Richer inspection for modern Glyphs files.** Path, glyph, and component
  reports now include shape-type counts, non-path shapes, group and attribute
  diagnostics, component `traverseAnchors`, raw node metadata, and focused
  compatibility warnings.
- **A hardened release pipeline.** Local publishing now fails closed around
  tests, signed tags, remote commit alignment, Developer ID signatures,
  notarization, Gatekeeper acceptance, exact release assets, and SHA-256
  checksums.

### Designed for compatibility

- Existing tool names and required arguments are unchanged.
- Legacy `get_glyph_paths` output remains valid input to `set_glyph_paths`.
- Glyphs 3.5 and Glyphs 4 are supported by the same plug-in bundle.
- Non-UI MCP clients receive the same feedback-tool information as text and
  structured output.
- Version-3 documents remain version 3 unless Glyphs itself upgrades them for a
  version-4-only feature.
- Unsafe rewrites involving node types that cannot be round-tripped are rejected
  before the layer is changed.

### Under the hood

- The bundled SDK reference now comes from the
  [official GlyphsSDK repository](https://github.com/schriftgestalt/GlyphsSDK),
  pinned to the documented Glyphs 4 revision.
- The documentation generator now lives in this repository, making reference
  builds reproducible without a private SDK fork.
- The source and Plugin Manager bundles share the same regenerated documentation
  and code.
- Codex marketplace skills are synchronized from the repository's canonical
  skill sources.
- The release is covered by metadata-preservation, rollback, schema, search,
  feedback-panel, marketplace, bundle-sync, installer, and Glyphs 3.5/4
  compatibility tests.

### Intentional scope

Version 1.3.0 adds safe compatibility, not direct authoring for every new Glyphs
4 feature. Dedicated controls for gradients, palettes, shape groups, contextual
kerning, smart-glyph axes, and higher-order interpolation remain planned for
future releases. Glyphs remains responsible for file-format conversion.

Learn more in the
[Glyphs 4 announcement](https://forum.glyphsapp.com/t/glyphs-file-format-documentation-version-4/36742)
and the
[official version 4 specification](https://github.com/schriftgestalt/GlyphsSDK/blob/Glyphs4/GlyphsFileFormat/GlyphsFileFormatv4.md).
