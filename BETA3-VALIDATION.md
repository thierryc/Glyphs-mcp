# Beta 3 validation record

Candidate: Glyphs MCP `2.0.0-beta.3`, desktop build 45, branch
`lit/v2-beta`.

Status: **published prerelease; automated and release-only qualification
complete; manual acceptance pending**. The signed tag is `v2.0.0-beta.3` at
commit `bdd4d0402c7498bf6611eea41ac62c786b22080a`. The stable Latest release
remains v1.11.1.

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
| Tagged release candidate Python suite | 1,939 passed, 2 skipped |
| Post-publication branch Python suite | 1,940 passed, 2 skipped |
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
is disclosed in `BETA.md`. This development installation does not itself prove
packaged or physical-Intel acceptance; packaged release evidence is recorded
separately below.

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

## Release evidence

- [x] Signed annotated tag `v2.0.0-beta.3` verifies with Thierry Charbonnel's
  release key and resolves to the exact pushed branch commit.
- [x] The payload, final app and DMG were accepted by Apple's notary service:
  `2595bdd5-838c-456c-aa1d-66385995b191`,
  `405bc360-daaf-42d1-89ec-74aa3ada470b` and
  `cb04f8ed-4630-466c-904a-d6649c69cd3c`.
- [x] Stapler validation and Gatekeeper assessment accept the app and DMG as
  Notarized Developer ID software from team `N9U29A4T8J`.
- [x] The extracted distribution verifies 88 Mach-O files, 47 signed bundles,
  installed-copy identities and the versioned Cursor ownership receipt.
- [x] The signed Sparkle archive and appcast verify against build 45 and the
  configured public key.
- [x] GitHub publishes the four exact assets as a non-Latest prerelease at
  <https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.3>.

Published SHA-256 values:

```text
f3e7af3a8dd4262258689803bca17f4d9b0a5c823218198eb76f712150c15900  Glyphs-MCP-2.0.0-beta.3.dmg
17a94148ffc5de3b24fa7d16b4342b52e7310763f8b46547974bd43cdc1b2950  Glyphs-MCP-2.0.0-beta.3.zip
c82e535612f2e954ba4158aa1e99c1abbd2c4b2f87ed6bb1db4fb54e3548239e  appcast.xml
```
