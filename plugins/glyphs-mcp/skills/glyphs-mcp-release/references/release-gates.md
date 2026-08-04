# Glyphs MCP release gates

Use this checklist from the repository root. Substitute the intended version
and tag explicitly; do not infer them from a dirty build directory.

## Phase 1: prepare a release candidate

Preparation is local and reversible. It may edit the working tree and run tests,
but it stops before commit, tag, push, signing, notarization, GitHub release
creation, or upload unless the user explicitly expands the scope.

1. Inspect state and provenance:

   ```bash
   git status --short --branch
   git branch --show-current
   git remote -v
   git log -1 --show-signature --format=fuller
   git tag --sort=-version:refname
   ```

   Compare with `origin/main` and the latest stable release. Fetch first when
   the local remote state may be stale and network access is authorized.

2. Align versions:

   ```bash
   python3 scripts/bump_version.py X.Y.Z
   python3 scripts/release_security.py metadata --repo-root . --tag vX.Y.Z
   ```

   Increment `CURRENT_PROJECT_VERSION` separately. Confirm both plug-in plists,
   `MARKETING_VERSION`, the installer build, README links, and command-set text.

3. Synchronize skill packaging:

   ```bash
   ./scripts/sync_codex_plugin_skills.sh
   ```

   Confirm every directory under `skills/` that belongs to the product appears
   in the sync list, terminal installer's `MANAGED_SKILL_NAMES`, packaged plug-in,
   docs table, and contract tests. Canonical and packaged trees must match.

4. Run targeted tests for touched code, then the mandatory complete gate:

   ```bash
   PYTHON_BIN=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 ./scripts/run_local_release_tests.sh
   ```

   Use another project-approved Python 3.11-3.14 interpreter only when the
   exact path and reason are recorded. The gate runs the complete Python suite,
   Xcode tests, shell syntax, patch whitespace, and an unsigned Debug build.

5. Build and validate documentation:

   ```bash
   cd website
   npm run build
   ```

   Run the standard skill creator's `quick_validate.py` once per canonical
   skill and once per packaged skill. Check local Markdown links inside skill
   packages and use stable GitHub URLs for repository references.

6. Verify generated surfaces:

   - Compare source and Plugin Manager runtime files byte-for-byte where they
     are required mirrors.
   - Compare canonical and packaged skill trees byte-for-byte.
   - Run documentation, profile, release-security, installer, marketplace, and
     Plugin Manager contract tests.
   - Run `git diff --check` after the final documentation edits.
   - Confirm no open font was mutated or saved.

7. Complete applicable manual QA from the release protocol on disposable font
   copies. Record app version, Python interpreter, font fixture, profile, tool
   calls, result, logs, and whether document/file state changed. Update-related
   releases must exercise notification-only discovery, explicit staging,
   cancellation/failure paths, signature/receipt checks, and no automatic
   replacement of the running plug-in. Label staging actions **Prepare Update**,
   keep **View Release** available after success, and document that 1.5.4 users
   must install 1.6.0 manually before later releases can be prepared.

## Phase 2: produce signed artifacts

Require explicit authorization before entering this phase. Work only from the
exact reviewed commit on clean `main`, with `origin/main` matching and an
annotated signed tag at `HEAD`.

```bash
./scripts/publish_release_assets.sh --tag vX.Y.Z --dry-run
```

The publisher reruns local tests, builds the signed Release app, signs the
nested plug-in payload and executable skill assets, notarizes and staples the
app/plug-in/DMG as designed, then verifies signatures, Team ID, hardened
runtime, secure timestamps, Gatekeeper, tickets, installed-copy identity,
versions, checksums, and the exact asset set. `SKIP_NOTARIZATION=1` output is
diagnostic only and is never publishable.

Expected assets are the versioned DMG, byte-identical latest DMG, stapled app
ZIP, and `SHA256SUMS`. Do not publish a standalone plug-in ZIP.

## Phase 3: upload verified assets

Require explicit authorization for commit/merge/tag/push and for GitHub draft
creation. Create the draft with no pre-existing assets. Then require the exact
tag confirmation for upload:

```bash
./scripts/publish_release_assets.sh --tag vX.Y.Z --skip-build --confirm-publish vX.Y.Z
```

Do not pass `--skip-build` unless the current files are the artifacts from the
successful exact-tag dry run. The publisher must still rerun tests and all
verification. It refuses dirty trees, non-`main`, remote mismatch, bad or
lightweight tags, published releases, duplicate asset names, signature or
notarization failures, and checksum drift.

Upload leaves the GitHub release as a draft. Public publication is a fourth,
separately authorized external action. Review notes, version, asset names,
checksums, signatures, and download behavior before publishing.
