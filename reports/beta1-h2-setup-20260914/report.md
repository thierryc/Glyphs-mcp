# H2 — consistent version, migration and setup guidance

**H2 passes its checks. Stop for user feedback before H3.** The current migration
and release guides now agree with Beta 1/build 43, the lean protocol and the
actual skill inventory. The corrected release skill is installed. No desktop
application, bridge or sidecar was installed or restarted, and nothing was
published.

## Changes and benefit

- Added [Version and identity](../../content/reference/version-identity.mdx),
  linked from migration, installation, settings and the documentation sidebar.
  It distinguishes product `2.0.0`, release `2.0.0-beta.1`, build `43`, lean
  interface revision `1`, bridge protocol `1`, and the negotiated MCP transport.
- Corrected the false bridge/protocol `0.1.0`, ten-skill and signed-candidate
  claims. The current inventory is eleven skills, seven tools and five jobs.
  Source labels, installed receipt data, live fingerprints and signed-release
  acceptance are described as separate evidence.
- Beta release guidance uses `lit/v2-beta/appcast.xml`, the prerelease tag and
  suffixed DMG/ZIP names. No beta Latest alias; `make_latest=false`. Stable feeds
  and releases remain separate. The instructions derive future labels/URLs from
  the existing release helper; no new version manager was added.
- Clarified connection-specific document-ID reuse and v1 coexistence on a
  separate free loopback port, with the exact native bundle identifiers.
- Documented H1's ownership/conflict behavior and sibling backup location.
  Retired specialized skills do not imply newly supported audit capabilities.
- Kept the release skill compact and added a focused, packaged identity/setup
  reference. Removed its stale default-branch documentation link.
- Corrected two desktop source labels: Welcome reuses `DesktopIdentity.versionLabel`;
  Troubleshooting no longer invents a fixed bridge version. The replacement
  notice now accurately says backups are outside skill discovery.
- Updated the existing Starter test to check its concrete endpoint, required
  tools and `document_id`, without requiring an obsolete contiguous prose phrase.

Example: **“Version 2.0.0 with protocol 1—is that a mismatch?”** now has a clear
answer: those are intentionally different identifiers. Verify each component's
release/fingerprint and the requested capabilities instead of comparing unrelated
version numbers.

## Verification

| Check | Result |
| --- | --- |
| Complete macOS installer suite | **179 passed, zero failures**, 11.173 seconds |
| Focused Python suite | **70 passed, zero failures, one optional Copilot skip**, 5.68 seconds |
| New H2 contract checks | Five passed: release table, exact skill inventory, stale claims, focused release reference, desktop copy |
| Previously failing Starter test | Passed in the complete macOS run |
| Documentation production build | Passed, with broken-link errors enabled |
| Skills and package checks | Eleven synchronized skills, valid release-skill metadata, validated candidate payload |
| Installed skills | One owned release skill updated; ten current; all eleven fingerprints match payload |
| Skill backup | Exact prior release-skill files verified at the logged sibling backup path |
| Runtime preservation | Sidecar and bridge before/after identities equal; seven tools and five jobs unchanged |
| v1 and historical documentation | Unchanged by source-hash comparison and the pinned snapshot regression |

[Test facts](test-results.json), [Python log](python-tests.log),
[macOS log](swift-tests.log.gz), [site-build log](docs-build.log),
[installation](installation.json), [backup log](installation.log),
[release helper output](source-identity.json) and [preservation](verification.json)
record the evidence. The tests passed on their first H2 run. Xcode needed its
usual build-service access; no failed sandbox retry was required in H2. The site
build emitted Node's non-failing localStorage warning.

Times above are test-suite execution times, not native callback or MCP latency.
This was not another font benchmark, and it makes no speed, token-saving or
native compatibility claim. The user-facing labels were compiled and checked in
source, not visually qualified in a newly installed desktop app.

## Installation and preservation

The existing installer automatically refreshed the unchanged owned release
skill; explicit overwrite was disabled. The [qualification driver](InstallSkills.swift)
is adapted from RV02 and delegates all writes to that installer. There were no
conflicts or unrelated replacements. A source/installed comparison covered all
eleven managed skills and preserved 1,706 other installed skill files.

The release target agrees with the live runtime:
`2.0.0-beta.1`, build 43; sidecar `82daa62ac227`, bridge `8b74a8d27ae4`,
Glyphs 4.1 (4107). Full before/after values are in [runtime evidence](runtime.json).
Only two read-only `get_status` calls were made. There was no document discovery,
font mutation, Save, export or Glyphs restart.

The checked source inventory contains 3,736 existing files. Changes are limited
to the listed H2 guides, skill entry, desktop copy, Starter test and sidebar,
plus the new focused references and tests. v1, runtime implementation, H1's
installer changes and earlier reports remain intact. Generated docs and candidate
payloads are local build artifacts.

The existing worktree contains substantial earlier desktop changes. The exact
[desktop/Starter/sidebar delta](desktop-source.patch.gz), with
[base/result identities](desktop-patch-identities.json), preserves these small H2
edits separately. Those source files remain in the existing uncommitted worktree;
this record does not claim a clean, independently releasable checkout. The reviewed
current setup pages, focused skill and H2 evidence are committed separately.

The installed desktop application retains its prior labels until an app update.
The documentation build is local and was not deployed. Public beta availability,
signing, notarization and signed-update acceptance were not requalified here.

## Judgment and next step

H2 removes contradictory setup instructions using existing identity and installer
mechanisms. It adds no runtime behavior or extra discovery call. The new focused
reference makes the distinction between product version and protocol practical
without adding that detail to ordinary font-read prompts.

**Next, after feedback: H3 — compact current context and Font View selection.**
Example: “Which glyphs and master have I selected?” should be answered directly
from bounded native evidence. H3 has not started.
