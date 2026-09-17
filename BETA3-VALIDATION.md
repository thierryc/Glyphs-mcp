# Beta 3 validation record

Candidate: Glyphs MCP `2.0.0-beta.3`, desktop build 45, branch
`lit/v2-beta`.

Status: **automated local qualification complete; manual acceptance pending**.
This record does not authorize or claim committing, tagging, pushing, signing,
notarizing, uploading or publishing the candidate.

## Source and payload invariants

- [x] Navigation exposes Setup and Project; the former Overview and Components
  destinations are absent from the current implementation.
- [x] The bulk queue contains Glyphs MCP, Curve Inspector and Reference
  Inspector followed by Codex, Claude Code, Claude Desktop and Cursor.
- [x] Component changes use one transaction; connector work is sequential and
  an individual connector failure does not stop later connectors.
- [x] The payload schema accepts only the Glyphs 4 target and rejects embedded
  `skills-v1` or a Glyphs 3 target.
- [x] The Cursor plugin is packaged with a versioned, hashed ownership receipt;
  update/remove tests cover backups, modified content and unowned content.
- [x] Scoped component update/remove tests preserve unrelated installed
  components and their recorded hashes.
- [x] The log collector tests missing, growing, malformed and oversized input,
  bounded persistence and secret redaction.
- [x] The disk-image source produces standard and Retina representations in a
  multi-resolution TIFF.
- [x] Canonical and packaged skills match after the final synchronization.
- [x] The complete local release suite and deterministic payload comparison
  pass after all Beta 3 changes.
- [x] Website production build, release-security candidate check, knowledge
  check and final `git diff --check` pass.

## Automated commands

Commands must be rerun from the exact final local candidate. Record their final
results here rather than carrying forward Beta 2 counts.

| Check | Result |
| --- | --- |
| Focused Beta 3 payload tests | 4 passed |
| Focused installer/configuration Python tests | 56 passed, 1 skipped |
| Complete Python suite | 1,938 passed, 2 skipped |
| Complete macOS installer suite | 195 test methods passed, including generated-payload verification |
| `./scripts/sync_codex_plugin_skills.sh` | 11 packaged skills synchronized |
| `PYTHON_BIN=.venv-v2/bin/python ./scripts/run_local_release_tests.sh` | Passed; no artifacts published |
| Website build and skill validation | Passed |
| Release-security candidate and local knowledge checks | Passed |
| `git diff --check` | Passed |

## Visible development-installation check

The final source was built and installed with development links on an Apple
silicon Mac running macOS 26.7, Glyphs 4.1 (4107), Xcode 26.3 and Swift 6.2.4.
The Setup page reported **Ready** with the current Beta 3 sidecar and bridge
identities, all three component cards and all four connection cards reported
Installed, and the authenticated management status route returned HTTP 200.
The Dactylotype Project comparison rendered a real geometry difference from
the same HEAD-to-working-tree change shown by the text diff.

The visible check also confirmed an existing Beta 2-era selection issue: after
switching glyph files, Visual can retain an unchanged master because master IDs
are shared between glyphs. Selecting a changed master displays the comparison;
the geometry worker returned the expected changed-layer IDs. This limitation
is disclosed in `BETA.md`. No packaged, signed or physical-Intel acceptance is
inferred from this development installation.

## Manual acceptance matrix

None of these rows is complete until it is exercised with the exact final
candidate and the machine, architecture, macOS, Glyphs and agent versions are
recorded.

| Scenario | Apple silicon | Intel | Required evidence |
| --- | --- | --- | --- |
| Fresh Install All | Unverified | Unverified | All 3 components and 4 connectors reach Installed |
| Partial component install/update/remove | Unverified | Unverified | Unrelated bundles and preferences preserved |
| Connector failure isolation and Retry | Unverified | Unverified | Later connectors continue; failed card retains detail |
| Cursor owned update/remove | Unverified | Unverified | Backup plus matching version/hash receipt |
| Cursor modified/unowned conflict | Unverified | Unverified | Content remains untouched and conflict is visible |
| Glyphs running with save prompt | Unverified | Unverified | Cancel and successful quit paths preserve work |
| Agent absent during Install All | Unverified | Unverified | Connector is configured without host detection |
| Reload/restart guidance | Unverified | Unverified | Each host discovers the new configuration after reload |
| Codex MCP reachability | Unverified | Unverified | Seven-tool catalog and current `get_status` identity |
| Claude Code MCP reachability | Unverified | Unverified | Seven-tool catalog and current `get_status` identity |
| Claude Desktop MCP reachability | Unverified | Unverified | Seven-tool catalog and current `get_status` identity |
| Cursor plugin reachability | Unverified | Unverified | Local plugin loads and reaches the MCP endpoint |
| Troubleshooting log window | Unverified | Unverified | Sources, refresh, copy, redaction and Reveal in Finder |
| Disk image at standard/Retina scale | Unverified | Unverified | Crisp copy, correct 680 × 420 point layout and icon positions |

## Release-only gates still excluded

Developer ID signatures, notarization, stapling, Gatekeeper, signed Sparkle
updates, final DMG mounting/extraction, public checksums and GitHub availability
belong to the separately authorized release phase. Do not infer any of them
from a local build or this record.
