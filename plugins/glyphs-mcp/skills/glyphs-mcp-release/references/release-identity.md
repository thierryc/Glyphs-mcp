# Release identity and setup checks

Work from the intended lean desktop checkout. Read `release.json`, run
`python3 scripts/desktop_release_identity.py`, and compare its output with
`skills/manifest.json` and the candidate manifest. Do not infer source, installed
or signed-release identity from each other.

The current unpublished target is product **2.0.0**, release **2.0.0**, stable
channel, beta number **0**, installer build **55**: **eleven managed skills**, thirteen MCP tools and up to 13
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

Use the helper's release tag and channel URLs. The published stable release uses
`v2.0.0`, `https://raw.githubusercontent.com/thierryc/Glyphs-mcp/main/appcast.xml`,
and `Glyphs-MCP-2.0.0.dmg` / `Glyphs-MCP-2.0.0.zip`. See the repository's
`V2-RELEASE.md` for completed signing and scoped native acceptance, and remaining
minimum-OS/manual limits. Source identity alone does not authorize publication.
The separate `lit/v2-beta/appcast.xml` also serves the signed stable update to
existing beta installations. New beta releases must use versioned beta filenames,
be GitHub prereleases with `make_latest=false`, and never publish a Latest alias.
Read `macos-installer/RELEASING.md` before release preparation; historical beta
instructions remain in the
[archived release plan](https://github.com/thierryc/Glyphs-mcp/blob/v2.0.0/BETA-LAUNCH.md).

Describe unsigned local checks, installation checks, signed/notarized artifact
checks and public availability separately. A successful build or source label
is not signed-release acceptance. Preserve historical measurements and v1 docs;
update current guidance only. This reference adds no publication authorization.

Keep packaged skill copies synchronized through
`scripts/sync_codex_plugin_skills.sh`. The installer refreshes unchanged owned
skills and preserves user-edited/unowned conflicts. Explicit **Replace preserved
skills (backup)** archives recognized retired private families and replaces
reviewed current conflicts. Backups and restoration coordinates are in the
sibling `glyphs-mcp-skill-backups` directory outside discovery; use the exact
paths in the installer log. Do not edit plugin caches or source worktrees as an
installation shortcut. Verify the configured files after installation and note
that a running task may retain its earlier skill catalog.
