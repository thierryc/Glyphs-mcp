# Release identity and setup checks

Work from the intended lean desktop checkout. Read `release.json`, run
`python3 scripts/desktop_release_identity.py`, and compare its output with
`skills/manifest.json` and the candidate manifest. Do not infer source, installed
or signed-release identity from each other.

The current unpublished target is product **2.0.2**, release **2.0.2**, stable
channel, beta number **0**, installer build **57**: **eleven managed skills**, eighteen MCP tools and up to 13
capability-gated job kinds. Sidecar and bridge product versions are coordinated; their code hashes
normally differ. The lean interface is `glyphs-mcp-sidecar`, interface revision
**1**, bridge protocol **1**. The dated MCP transport version is negotiated
separately. Independent companions retain their own versions. The v2
payload is Glyphs 4-only; the pinned Glyphs 3 **1.11.0** source metadata and
separate release retain their identity.

For installation verification, compare a fresh `get_status` with the exact
candidate/receipt: `release`, sidecar `runtimeId`/`codeHash`, and independent
`bridge.release`, `bridge.runtimeId`, `bridge.codeHash` and `bridge.host`.
These are initialization-time file fingerprints, not in-memory code hashes.
Missing identity is unavailable evidence; changed files do not prove a running
process reloaded them. Identity checks need no font discovery or Save.

Use the helper's release tag and channel URLs. This candidate selects
`v2.0.2`, `https://raw.githubusercontent.com/thierryc/Glyphs-mcp/main/appcast.xml`,
and planned `Glyphs-MCP-2.0.2.dmg` / `Glyphs-MCP-2.0.2.zip`. Its signing and
native acceptance must be verified separately before publication.
The published stable 2.0.1 release and its `V2.0.1-RELEASE.md` evidence remain intact;
that evidence does not qualify this candidate. Source identity alone does not
authorize publication. The separate `lit/v2-beta/appcast.xml` serves the
published stable update to existing beta installations. New beta releases use
versioned beta filenames, are GitHub prereleases with `make_latest=false`, and
never publish a Latest alias. Read `macos-installer/RELEASING.md` before release
preparation; historical beta instructions remain in the
[archived release plan](https://github.com/thierryc/Glyphs-mcp/blob/v2.0.0/BETA-LAUNCH.md).

Describe unsigned local checks, installation checks, signed/notarized artifact
checks and public availability separately. A successful build or source label
is not signed-release acceptance. Preserve historical measurements and v1 docs;
update current guidance only. This reference adds no publication authorization.

Compiled comparisons require `font.compare.diffenator.v1` in the separate
`comparisonCapabilities` list. Optional Diffenator/Beztrace download catalog
entries remain unavailable until signed distributions and architecture acceptance
exist; source checks and an unsigned desktop build do not qualify those assets.

Keep packaged skill copies synchronized through
`scripts/sync_codex_plugin_skills.sh`. The installer refreshes unchanged owned
skills and preserves user-edited/unowned conflicts. Explicit **Replace preserved
skills (backup)** archives recognized retired private families and replaces
reviewed current conflicts. Backups and restoration coordinates are in the
sibling `glyphs-mcp-skill-backups` directory outside discovery; use the exact
paths in the installer log. Do not edit plugin caches or source worktrees as an
installation shortcut. Verify the configured files after installation and note
that a running task may retain its earlier skill catalog.
