# Release identity and setup checks

Work from the intended lean desktop checkout. Read `release.json`, run
`python3 scripts/desktop_release_identity.py`, and compare its output with
`skills/manifest.json` and the candidate manifest. Do not infer source, installed
or signed-release identity from each other.

The current target is product **2.0.0**, release **2.0.0-beta.5**, beta number **5**,
installer build **47**: **eleven managed skills**, nine MCP tools and up to nine
capability-gated job kinds. Sidecar and bridge product versions are coordinated; their code hashes
normally differ. The lean interface is `glyphs-mcp-sidecar`, interface revision
**1**, bridge protocol **1**. The dated MCP transport version is negotiated
separately. Independent companions retain their own versions. The Beta 5
payload is Glyphs 4-only; the pinned Glyphs 3 **1.11.0** source metadata and
separate release retain their identity.

For installation verification, compare a fresh `get_status` with the exact
candidate/receipt: `release`, sidecar `runtimeId`/`codeHash`, and independent
`bridge.release`, `bridge.runtimeId`, `bridge.codeHash` and `bridge.host`.
These are initialization-time file fingerprints, not in-memory code hashes.
Missing identity is unavailable evidence; changed files do not prove a running
process reloaded them. Identity checks need no font discovery or Save.

Use the helper's release tag and channel URLs. Beta 5 uses `v2.0.0-beta.5` and
`lit/v2-beta`, including
`https://raw.githubusercontent.com/thierryc/Glyphs-mcp/lit/v2-beta/appcast.xml`.
Beta DMG and ZIP names include `2.0.0-beta.5`. Do not publish a beta Latest alias;
its GitHub release is a prerelease with `make_latest=false`. Stable release feeds
and Latest aliases belong to their separate release process. Read
`BETA-LAUNCH.md` and `macos-installer/RELEASING.md` before release preparation.

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
