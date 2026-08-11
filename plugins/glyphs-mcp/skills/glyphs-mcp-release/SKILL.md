---
name: glyphs-mcp-release
description: Prepare, audit, build, sign, notarize, or publish a Glyphs MCP release. Use when asked to bump a release version, assemble release notes, synchronize bundled skills or plug-in mirrors, run release gates, prepare signed installer artifacts, create a release tag or draft, upload verified assets, or perform final publication checks in the Glyphs-mcp repository.
---

# Glyphs MCP Release

Treat preparation, signed artifact production, asset upload, and public release as separate authorization boundaries.

## Establish the release state

1. Work from the Glyphs MCP repository root. Read `CODEX.md`, the current changelog, and the canonical release documentation before changing anything.
2. Inspect the branch, worktree, index, remotes, latest release tag, and divergence from `main`. Preserve unrelated or uncommitted work; never discard it to make a release gate pass.
3. Identify the exact semantic version, installer build number, release base commit, intended branch, and requested phase. Default to local release-candidate preparation when the user has not authorized an external action.
4. Record any safety stash or backup created during integration. Do not drop it until the restored tree and release candidate are verified.

## Prepare the candidate

1. Run `scripts/bump_version.py X.Y.Z`, increment the integer installer build, and verify both plug-in plists, Xcode marketing/build versions, download links, and command-set version text.
2. Synchronize source and Plugin Manager runtime files using the repository packaging path appropriate to the change. Inspect the resulting diff; do not overwrite unrelated bundle work.
3. Add every canonical skill to `scripts/sync_codex_plugin_skills.sh` and `MANAGED_SKILL_NAMES`, then run the synchronization script. Treat `skills/` as canonical and `plugins/glyphs-mcp/skills/` as generated.
4. Update `CHANGELOG.md`, public setup/skill documentation, command/reference pages, and `content/contributor/release-build-notes.mdx`. Keep claims tied to tests actually run.
5. Update the production tool catalog, schemas, prompts, routing fixtures, and release-surface tests whenever a public tool or result contract changed.

## Validate locally

1. Run focused tests while iterating, then the complete local release gate with an accepted Python interpreter.
2. Build the documentation website and validate every canonical and packaged skill with `quick_validate.py`.
3. Run release metadata, catalog/documentation, installer, plug-in mirror, and packaged-skill synchronization checks. Run `git diff --check` last.
4. Perform the applicable manual matrix from the release QA protocol on disposable copies. Use Glyphs 3.5 and Glyphs 4 when compatibility is in scope.
5. Never save an open font automatically. Snapshot document/file state for live read-only checks and report whether it remained unchanged.
6. For staging-only updater releases, require **Prepare Update** wording, an explicit not-installed state, a trusted release link, and proof that the installed plug-in remains unchanged.

Use the exact commands and phase gates in [Release gates](references/release-gates.md).

## Stop at the authorization boundary

- Local preparation does not authorize committing, merging, tagging, pushing, signing, notarizing, creating a GitHub release, uploading assets, or publishing a draft.
- Before signed artifact production, require the exact reviewed release commit on clean `main`, a matching remote `main`, and an annotated signed tag at `HEAD`.
- Before upload, require an empty draft for the exact tag and the publisher's exact-tag confirmation. Never use `--allow-unsigned-tag` or bypass notarization unless the user separately authorizes that exception after reviewing the risk.
- Keep uploaded releases as drafts until the user explicitly authorizes public publication. Never replace an already distributed asset; prepare a patch release instead.

## Report the handoff

Report the version/build, base and branch, every changed release surface, synchronization status, commands and exact results, manual checks completed or outstanding, artifact/signature state, and every external action not taken. Distinguish a prepared candidate from a publishable signed tag.

Canonical project documentation:

- [Installer release procedure](https://github.com/thierryc/Glyphs-mcp/blob/main/macos-installer/RELEASING.md)
- [Release QA protocol](https://github.com/thierryc/Glyphs-mcp/blob/main/content/contributor/release-qa-protocol.mdx)
- [Release and build notes](https://github.com/thierryc/Glyphs-mcp/blob/main/content/contributor/release-build-notes.mdx)
