# Milestone 7 — Desktop implementation

> Historical development record. The unpublished 2.1.0 candidate was retired
> in favor of **2.0.0 Beta 1, build 43**. Version numbers, installation states
> and artifact paths below describe past local tests, not a current release.
> Use [BETA.md](BETA.md) for the current candidate.

The authorized implementation is Glyphs MCP Desktop 2.1.0, build 30, bridge
(0.1.0). Work only in this worktree (`lit/milestone-7`). The Milestone 6
candidate, original v2 worktree, and original fonts must remain unchanged.

## Preservation

- Complete archive: `../archive/milestone6-complete.tar.gz`.
- SHA-256: `35a0e0c0218a398fba0efea1674dfea8dc6152ef1f290196ff57b41482bfcee6`.
- All 209,281 archive entries and 209,256 copied candidate entries verified.
- Base commit: `13ca80561a1c0f2addc8e0aa5dd3a78a0de076a0`; imported uncommitted
  candidate and versioned documentation preserved. No commits or public writes.

## Implementation sequence

1. Application shell and installation adoption — implemented; live adoption opens Overview.
2. Shared activity, authenticated controls, reservation and restart tests — implemented.
3. Menu bar, Regular-S source icon, login opt-in, lifecycle/accessibility — implemented; native visual acceptance pending.
4. Local/cached/public templates and strictly read-only Git inspection — implemented; focused Swift tests pass.
5. Sparkle integration and local signing/feed scripts — implemented; signing, update trial and migration acceptance pending.
6. Full local checks, signed/notarized installation and three native cycles.

## Locked decisions

- Three sidebar destinations: Overview, Components, Projects.
- Menu bar shown by default; login startup separate, opt-in, initially off.
- Git shows branch/status/diffs only; no Git modifications or remote commands.
- Seven MCP tools stay unchanged; optional activity fields and private routes.
- No GitHub Actions, publishing, embedded AI chat, or final welcome design.
- Source icon: `litsquare.logo.glyphsMCP`, Regular-S master
  `74EE9863-DD0D-47A4-B98B-F1098734EDA9`, from the user's LitSquare icon package.
- Sparkle 2.9.6 archive verified against upstream SHA-256
  `52bf9e88cdd972fc0c81501377a880e90d47031bd8ca5462488f843e2609e192`.

## Acceptance

Record actual checks and artifact paths here as each stage passes. Live font
acceptance is authorized on disposable copies only. Preserve native Save,
Undo/Redo/Revert, exact restoration, and companion redraw behavior. Record
baseline/loaded responsiveness separately; 200 ms is diagnostic.

## Current implementation evidence (2026-09-07)

- Full Python suite: **1,210 passed, 3 skipped** (`build/milestone7-python-suite.log`).
- Desktop/project Swift tests: **13 passed**, covering adoption, login defaults,
  visibility sampling, archive safety, offline cache, cancellation, collision
  preservation and Git index/reference/worktree immutability
  (`build/desktop-projects-tests.log`). Later small monitor/support edits still
  need the full Swift run.
- Activity/control group: 50 passed before the additional installer/native-panel
  regression tests. Focused installation/version/docs checks: 63 passed, 1 skipped.
- v2 documentation typecheck and production build pass. The v1 snapshot hash
  test passes; its source files have not been edited.
- Lean package/skill check: 10 skills, 7 public tools, both runtime architectures.
- Native debug app opened through CUA: Overview/Components/Projects, version
  **2.1.0 (0.1.0) · Build 30** visible. It correctly explains that the installed
  M6 sidecar lacks the new private activity routes. The debug app remains open.
  The first CUA call took 1,465 seconds to return; bound future calls explicitly.
- Sparkle 2.9.6 is checksum-pinned in `third_party/sparkle.json`. Its private
  update key is stored only in Keychain, account `cx.ap.glyphsMcp`; public key:
  `K5EkYQQZFhOWgsw2dtO2dPnCry+8VKhG0eHYeUd2iP8=`.
- Regular-S menu icon exported to `Resources/Assets.xcassets/GlyphsMCPMenu.imageset`.
  Three positive contours and one subtractive mask are retained in vector PDF.
  Provenance/fingerprints: `third_party/desktop-icon.json`.
- Public template registry pins Google Fonts project template revision
  `d52f47ca69c2d9e16a925501e6af0afc8df1fd51`, ZIP SHA-256
  `94e6a598d6e59158508f4b815deffb6c99f5f4eea287045d3a7fca162091a553`.

## Remaining release work

1. Complete focused coverage for interrupted downloads/checksum rejection,
   worker running/exit observations, stale UI observations and installation
   recovery. Review async lifetime and update/install races.
2. Resolve the one-time M6-to-desktop transition safely: the currently installed
   M6 service has no private idle-reservation route and uses an ephemeral JobStore.
   New controls deliberately refuse its 404 response. Preserve prepared results
   and identities; do not silently bypass the busy guard or infer idle from a
   slow/missing reply. New M7 restarts use the stable managed `lean-v2/jobs` store.
3. Run full Swift/companion/Python suites, unsigned deterministic builds,
   documentation/skill/module-budget checks, and `git diff --check`.
4. Finish release notices/provenance and v2 maintainer instructions. Check all
   artifact paths after the app rename. Existing v1 updater classes/scripts are
   retained for compatibility, but desktop update UI uses only Sparkle.
5. Build/sign/notarize app and DMG using `scripts/build_desktop_release.sh`,
   verify Sparkle nested helper signatures and update feed, perform a real signed
   older-to-newer update trial and negative-signature/download/migration checks.
6. Install and restart Glyphs safely; verify menu icon, panel/companions and
   placeholder lifecycle; run the original-source hash/native-save-control gate
   three consecutive times with desktop monitor visible. Test background identity
   on a clean account/VM if available, and accurately record any unavailable gate.

Nothing from Milestone 7 has been installed or publicly published yet. No fonts
have been edited by the desktop implementation work.

## Signed candidate and installation (2026-09-07)

- Final production Python suite: **1,216 passed, 3 skipped**. Full local release gate passed, including the full Python runtime matrix, 133 Swift tests, documentation, skill checks, budgets and deterministic unsigned payloads. A subsequent focused Swift run passed all 9 project tests after improving the ordinary-folder Git message.
- Closed two clean Glyphs documents normally and quit Glyphs. No source-font changes. Stopped the pre-desktop service using its existing helper; its old wrapper required its original non-isolated invocation, corrected by M7 entry wrappers.
- The authoritative M6 temporary JobStore was identified through the then-current `get_job` calls. All four jobs were cancelled/discarded. Copied it byte-for-byte into stable managed storage; evidence in `build/desktop-acceptance/job-migration.json`.
- Installed signed M7 bridge, sidecar/runtime and both companions through verified payload installer transaction. Receipt: `build/desktop-acceptance/installation-result.json`. Authentication hash, port 9680 and startup preferences preserved. M7 service is running, private controlProtocol 1 responds, both companions registered after native Glyphs restart.
- Developer ID/notarization complete for payload, app and DMG. Release verifier passed. App accepted by Gatekeeper, installed at `/Applications/Glyphs MCP.app`.
- Release archive SHA256: `cff83afcb9d9f5809c99aa0d64609268051b2d73e041245edacea396dc938dbe`.
- DMG SHA256: `b2cdf2830c4e728c117ec085a92084df4cb7342fea9bcfd8fe841dc7e5a2461b`.
- Signed appcast SHA256: `f07142933e63a0d12d3567aef64a879695be763f4b5602b35ad678086290e895`.
- Real Sparkle trial: signed/notarized lowered-version fixture 2.0.99/build29 upgraded through native UI to production 2.1.0/build30. Installed bundle identity equals release exactly; component receipt and all job records unchanged. Invalid feed, invalid archive signature and interrupted download each rejected with build29 preserved. Evidence: `build/update-trial/observations.json`.
- Final signed runtime offline startup passed both architectures (HTTP + stdio then-current catalogs): arm64 5.139s, x86_64 13.118s.
- Native UI verified welcome repeatedly opens, Settings defaults (menu on, desktop login off, sidecar startup preserved on, automatic updates off), receipt adoption and disposable starter creation. Starter project: `/private/tmp/Glyphs MCP Desktop Acceptance`.
- Offscreen AppKit icon rendering verified light/dark 1x/2x with preserved mask and contours: `build/desktop-icon-acceptance/icon-rendering.png`.

## Remaining live checks / current handoff

Fresh source/control copies created and natively saved in `/private/var/folders/x5/fygm197n4zg2k5l0shskngr80000gr/T/glyphs-m7-live-momqdse5`. Original source hash remains `sha256:7f87019f3fe677999f7c45f498ef5d68e2ba1a2d21ded2cd2387c56f1354e5b2`. Config and new M7 phased harness are `build/desktop-acceptance/config.json` and `scripts/qualify_milestone7_live.py`.

Glyphs is running with M7 components and a file-picker Go To sheet. Native automation accepts the disposable path but confirmation returns to `/`; asked the user to open the disposable font and reply opened. Mac lock state verified unlocked. Do not mark the three visible font cycles complete: none have run for M7 yet.

Asked whether a clean macOS account/VM is available for background-item identity. VirtualBuddy is installed with an existing Jittery Squid VM, but its cleanliness and access are unknown. No VM has been launched or changed.

Avoid CUA getApp(SystemUIServer): it stalled for 623 seconds despite a 30s requested timeout. Known application paths are fast. Native UI clicks usually work; keyboard/file-picker automation is unreliable. The installed app is now the final production 2.1.0 build30 after the successful update. Its feed points to GitHub again, not the local trial feed.

Public publication remains separate and has not occurred.

## Final review corrections and verified installation

The live port round-trip exposed a preflight socket using different reuse semantics from the HTTP listener: recently closed connections incorrectly blocked returning to port 9680. Added real-socket regressions and SO_REUSEADDR; occupied live listeners remain rejected.

The installer now always takes the shared control lock and idle guard, even when --start is omitted or a component is removed. The startup choice affects only the post-install start. Failed replacement restores prior running intent. Loading the verified control module no longer emits bytecode into its immutable payload; a real failed install proved full rollback before this was corrected. Focused tests cover busy refusal with/without start, removal, failure recovery, and unchanged payload identity.

The complete Swift run exposed a process timeout race (termination exit 15 beating the timeout error). A shared locked timeout marker now preserves the timeout result in both capturing and streaming calls. Both timeout tests passed 20 iterations; the subsequent full local release gate passed. Final gate/build logs: build/milestone7-release-gate-final.log and build/milestone7-release-build-final.log.

Final app and components installed from the final notarized payload. Receipt: build/desktop-acceptance/installation-result.json. The real signed 2.0.99/build29 -> 2.1.0/build30 Sparkle update was repeated with the final archive; installed app identity equals release exactly, production GitHub feed restored, Gatekeeper accepted. Evidence: build/update-trial/observations-final.json. Local update fixture server currently runs on 18473 and must be stopped after acceptance.

Final update ZIP SHA256: 902a3e9ab3a11921bfe6fe5ffb223f910cc98a1a581bd9b675218eb1c068c88e. Final appcast SHA256: 7e05f482a5f32c5caa7dd23e172add18115de8422d890ee04bb0f92b8716090c. Final artifact verification passed with --tag v2.1.0 --write-checksums.

Live shared controls passed Stop/Start, immediate port round-trip, idle reservation refusal, and prepared-result preservation across restarts; original port 9680, preferences and receipt preserved. Evidence: build/desktop-acceptance/live-controls.json. Dashboard closing stopped all private status requests for 38 seconds; explicit desktop Quit left the same service PID running. Evidence: monitor-hidden.json and desktop-quit.json in that folder.

### Acceptance setup correction — do not repeat the failed setup

The worker's private _load_font intentionally sets grid=0 for analysis and must never be used to make a saved control. The original M7 setup mistakenly reused it. Corrected scripts/prepare_desktop_acceptance.py and scripts/qualify_milestone7_native.py now use unmodified native GSFont loading. Earlier grid-zero trials and their differences are retained under build/desktop-acceptance/preliminary and preliminary-grid-zero.

Even an unmodified detached Save leaves some automatic-component caches stale compared with native editor Open/Save. The final untouched control was opened in Glyphs, read across all 3807 master layers (exactly matching the pre-operation baseline), and saved through native File > Save without any MCP operation. The test font then matched all 450 design files exactly. Evidence: control-native-open-original-grid.json and control-native-save-original-grid.json. This required no production geometry change or relaxed comparisons. The control remains grid=1. Detached native three-cycle qualification rerun passed with grid=1 preserved and exact native-save equality (build/desktop-native-heavy.json).

Current final native pair: /private/var/folders/x5/fygm197n4zg2k5l0shskngr80000gr/T/glyphs-m7-live-5y2w26yf. Current config is build/desktop-acceptance/config.json, nativeEditorControlPrepared=true. Original source hash remains sha256:7f87019f3fe677999f7c45f498ef5d68e2ba1a2d21ded2cd2387c56f1354e5b2. Original-grid warmup trial retained in original-grid-warmup. Final three full cycles started only after final app update and final component installation; cycle 1 spacing is now running. None of the three final cycles is yet complete.

CUA pitfalls: getAXState after Quit relaunches an app; do not observe immediately after quitting when testing process exit. KP_Enter confirms native Go To sheets; Return does not reliably do so. New-app discovery stalled for Finder for 395 seconds, SystemUIServer for 623 seconds, and earlier debug app for 1465 seconds despite requested timeouts. Avoid further broad/native app discovery. Native menu commands in Glyphs and Glyphs MCP work reliably; SwiftUI sidebar mouse clicks sometimes do nothing. Restarting desktop resets it to Overview. No clean account/VM identity verification or actual global menu-bar popover visual inspection has been completed yet.

## Final native desktop acceptance (supersedes pending notes above)

Final qualifying monitored font cycles **3, 4 and 5 passed**. Each applied 2,634 spacing writes across 3,807 master layers, passed exact per-glyph native Undo/Redo, restored the whole spacing job, applied exact fractional widths to 3,839 layers, passed native Revert and both preparation/application cancellation recovery, and matched all 450 native-control design files on Save. Original full package hash remains unchanged. Cycles 1/2 are retained as preliminary evidence; cycle 1 explicitly resumed a ready job after a pre-apply read error, never a replacement mutation.

The dashboard must be explicitly activated through File > Open Glyphs MCP for visible-monitor acceptance. CUA otherwise operates background windows, whose fully occluded state correctly pauses monitoring. Native AX confirmed automatic preparation/elapsed/worker feedback and changes counts. The user opened the menu-bar logo; closing the dashboard then exposed the native popover to CUA. Popover content, accessible controls and reopening Overview passed. Three normal Glyphs restarts verified companion persistence, with reference Loading changing to No changes without canvas interaction on the second restart. The final viewport needed framing to show the glyph.

An extra native keyboard node edit/Undo after restart quantized x=216.25 to 217 then 216. Exact readback caught this outside the MCP exact-write helper. Native Revert restored the exact baseline before any save. Do not claim ordinary native keyboard Undo passed exactness; MCP-operation Undo/Redo did pass. Evidence is retained in companion-native.json and cycle-3-node-undo-exact.log.

Cancelled native Glyphs closure was exercised from Components with the final fractional job applied. Cancel kept the document open and Install disabled; no installed records, authentication or launch-agent preferences changed. Restart from Overview retained the same applied job identity and all values exactly. Signed app, all installed components and receipt identities still match final release. Local Sparkle fixture server on 18473 was stopped.

Final gate: **1,224 Python passed, 2 skipped; 134 Swift passed**. Final documentation rebuild, skill/package checks, strict code signature, Gatekeeper, stapled notarization validation and git diff --check passed. Installed app is universal arm64/x86_64 with macOS 13 baseline; acceptance host macOS 26.7, Glyphs 4.0.1 (4004).

Report and machine summary: build/desktop-acceptance/report.md and summary.json. One final preparation phase had a 236.962 ms maximum (20.020 ms p95, no errors); a no-apply diagnostic preparation repeat is being collected under cycle-6.json. The 200 ms limit remains diagnostic.

Remaining external gate: clean-account/VM background name/icon and actual login launch. Current-account sfltool records signer Thierry Charbonnel/N9U29A4T8J and AssociatedBundleIdentifiers cx.ap.glyphsMcp, but retains legacy name python3. No clean VM/account was available in this session. The early-2.0.0 safe manual-stop/temporary-job limitation is documented. Public publication remains separate.

Diagnostic repeat complete: spacing preparation without apply passed, 9.803 ms p95, 118.935 ms maximum, no errors; original/control unchanged. The >200 ms sample did not recur.
