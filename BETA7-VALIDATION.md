# Beta 7 preparation record

Source target: Glyphs MCP `2.0.0-beta.7`, desktop build 49, branch
`lit/v2-beta`.

Status: **local feature candidate verified; unreleased.**

## September 23, 2026

- Advanced beta metadata and both installer build configurations with
  `scripts/bump_version.py --beta 7 --installer-build 49 2.0.0`.
- Updated current source guidance and the packaged release skill.
- Kept the published Beta 6 download URLs, signed appcast and historical
  qualification records intact. Glyphs 3 remains pinned to 1.11.0.
- The latest published installation target is Beta 6/build 48. Local
  installation and cleanup evidence is recorded separately below.

Broader Beta 7 native/client release acceptance, signing, notarization, signed
update and publication gates remain pending. Beta 6 results are not Beta 7 evidence.

## Local checks

- 25 focused beta identity, version bump, documentation and release-skill tests passed.
- 20 desktop build/cleanup contract tests passed.
- Lean package contract passed: twelve tools, eleven managed skills, both runtime architectures.
- All eleven packaged skills match their canonical sources.
- Documentation production build and `git diff --check` passed. Node emitted
  the existing localStorage experimental warning.
- The signed Beta 6 `appcast.xml` is byte-for-byte unchanged.

## Installed release

Installed the latest published **Beta 6/build 48** into
`/Applications/Glyphs MCP.app`, replacing the unsigned local build. Developer ID
signature verification, Gatekeeper and the stapled notarization ticket passed.
The exact embedded signed payload passed verification of 94 Mach-O files and
47 bundles before its transactional installation into Glyphs 4.

After the explicitly authorized native save, Glyphs was restarted and the font
reopened without an unsaved-change indicator. The app's Setup shows **Ready**,
Beta 6/build 48 and all three components installed. Fresh live status reports
Glyphs 4.1 (4107), both inspectors and the available worker, with sidecar and
bridge identities matching the installation receipt independently:

- Sidecar: `sha256:6fe1d1da74cafadc39720260e4eb7518f6e431abbfdf84dab9d7263e86e1fc4a`.
- Bridge: `sha256:54c06f5f0ee25c28d6b76f675e7ea9f679074fc83c8df1a4f0876504598b8e38`.

Local evidence (not public release assets):
`build/reports/beta6-signed-app-install-20260923.json`,
`build/reports/beta6-signed-components-install-20260923.json`, and
`build/reports/beta6-installed-status-20260923.json`.
The installed component receipt remains in
`~/Library/Application Support/Glyphs MCP/lean-v2/installation.json`.

## Cleanup

Removed generated files totaling **8,820,807,633 bytes (8.82 GB)**,
including nine obsolete app backups, duplicate payloads, archived Xcode build
products, update-test application/archive copies and regenerable caches.
This is the summed file size removed; APFS sharing and snapshots can make the
change in physical free space differ. Source worktrees, dependency caches,
installation rollback material, historical reports and versioned release
archives were retained. Each removal was scoped and checked for tracked files
or source worktrees where applicable.

Receipts: `build/reports/beta7-standard-cleanup-20260923.json`,
`beta7-generated-cleanup-20260923.json`, `beta7-old-app-cleanup-20260923.json`
and `beta7-cache-cleanup-20260923.json` in the same directory.

Retained verified Beta 6 archives:

| Artifact | SHA-256 |
| --- | --- |
| `dist/Glyphs-MCP-2.0.0-beta.6.dmg` | `578c7d9f362826dd7da6cc21118d35c8684ef2ab09f6bf231f7723685dc81ac1` |
| `dist/desktop-update/Glyphs-MCP-2.0.0-beta.6.zip` | `8cbde8127e4c78360f1cfc9380a31cd0e91efff326428eb177ae95aef65e2c64` |

The metadata-only preparation did not build or install Beta 7. The subsequent
template feature check below builds a local candidate without installing it.
No tag, Developer ID signing, notarization submission or publication was
performed during this preparation. The source and preparation changes were
subsequently approved for a local commit only, with no push.


## Template menus and favorites

- Unified built-in, registry and local templates in one catalog. Favorites sort
  first, with Finder-style alphabetical ordering within both groups and stable
  identity tie-breakers. Preferences survive restarts, refreshes and temporarily
  absent registry entries; new installations start without favorites.
- Added accessible three-dot menus and filled-star favorite indicators. GitHub
  source links select the pinned template directory; Issues opens repository
  issues. Local Reveal in Finder selects the original folder and reports a
  missing folder clearly. Starter templates have only the favorite action.
- Corrected the planned Stargazers link after observing GitHub's 404. GitHub
  restricted that view in 2026; **Star on GitHub…** instead opens the repository
  root with its public Star control. Local favorites do not star repositories.
- Preserved registry schema, MCP interfaces and the existing creation workflow.

Validation:

- Full macOS installer suite: **210 tests passed**. After correcting the Star
  destination, all **7 catalog/link tests passed** again. Coverage includes mixed
  sources, multiple favorites, removal, numeric/case sorting, duplicate names,
  normalized paths, preference reload, registry revision/absence and URL encoding.
- Full Python matrix: **2,149 passed, 1 skipped**. An initial sandboxed run could
  not bind two local test sockets; the complete rerun passed with socket access.
- Documentation production build, lean package contract, skill synchronization
  and two independent deterministic payload builds passed.
- Native UI verified menus, indicators, immediate favorite/unfavorite ordering,
  persistence after restart, pinned GitHub source, Issues and original-folder
  Finder selection. The rebuilt Star on GitHub action loaded the repository root
  and its public star control successfully. A newly fetched registry entry also
  appeared in the correct alphabetical position. Built-in Use Template
  successfully created a disposable project; its recent entry and test favorites were restored afterward.
- Local build and verification evidence: `dist/local/build-receipt.json`,
  `build/reports/beta7-template-local-app.log`,
  `build/reports/beta7-template-app-verification.json`,
  `build/reports/beta7-template-installer-tests.log`,
  `build/reports/beta7-template-star-tests.log`, and
  `build/reports/beta7-template-python-tests-unsandboxed.log`.

The locally built app is `dist/local/Glyphs MCP.app` (Beta 7/build 49). It is a
local test artifact, not a signed distribution candidate.

## September 24, 2026 — local installation and push preparation

- Closed both running Glyphs MCP app copies. Replaced the installed Beta 6
  manager with the receipt-verified local Beta 7/build 49 app, launched it from
  `/Applications/Glyphs MCP.app`, then removed the replaced Beta 6 app copy.
- Ran **Install All** while Glyphs 4 was closed. The installation receipt records
  installer build 49, Beta 7 bridge identity, and all three Glyphs components.
  Glyphs has not been relaunched to verify the new bridge in a live font session.
- Codex, Claude Desktop and Cursor configuration completed. Claude Code
  configuration preserved four existing modified or unowned skills and reports
  that connection as needing attention. Those user files were left intact.
- The full macOS installer suite passed **210 tests** after the Option-scroll
  direction and equal-height Setup card changes. The focused desktop Python
  checks passed **20 tests**; lean package and skill synchronization checks
  passed. The current app still passes its source-bound build receipt check.
- Removed the replaced build 48 app and obsolete build 43 and 47 app backups.
  Removed the temporary Xcode test DerivedData after the suite passed. The
  repository cleanup inspection found no remaining generated outputs on its
  removal list. Checkout-only guidance remains untracked and unstaged.
- Fetched `origin/lit/v2-beta` and confirmed the local branch contains the
  remote branch with no incoming commits. No source changes were pushed.
- The local app is an unsigned Debug build. Developer ID signing, notarization,
  full release qualification, signed update and publication remain pending.
  The source branch can be pushed independently of those distribution gates.
