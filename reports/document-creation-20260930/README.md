# Font creation implementation and installation

The new `create_document(family_name, idempotency_key, units_per_em=1000)` tool
creates an unsaved font with one Regular master and one Regular instance. Native
creation runs on Glyphs' main thread. `save_document` remains the separate verified
Save/Save As operation. Creation requires `document.create.v1` and returns native
document, master and instance identities.

Retries retain the same request and native outcome. The sidecar journals before
dispatch with a process-shared lock and durable atomic write. A changed request
conflicts; closing a created font never recreates it. A different bridge session
requires reconciliation rather than replay. Native partial failures report the
owned document when discoverable. The bridge limits creation records without
retaining completed whole font objects or evicting duplicate-protection keys.

## Verification

- 193 focused creation, save, protocol, catalog, package, documentation, workflow
  and deterministic-build tests passed.
- 20 server-control regressions passed with loopback permission; sandbox-only
  listener errors were environmental.
- Both `.glyphs` and `.glyphspackage` passed production native constructor,
  serialization and direct-native-reader reopening in Glyphs 4.1/build 4107.
  See `detached-native.json`. The worker's LaunchServices package reopening
  failed; `package-probe.json` records the type-lookup error and successful direct
  native reads with and without a seeded glyph, in formats 3 and 4.
- Packaged FastMCP discovery exposes thirteen tools and the expected creation schema.
- Lean package validation and synchronization of all eleven managed skills passed.
- The scoped installer's native preflight passed.
- Live MCP verification passed on Glyphs 4.1.1/build 4108: creation, duplicate
  request reuse, master reads and Save As in both supported formats. The saved
  files reopened through the native reader with their native IDs preserved.
  See `live-verification.json` and `live-native-reopen.json`.
- The freshly built desktop app passed bundle and build-receipt verification.
  The installed executable was confirmed running from `/Applications`.
- `git diff --check` passed.

The initial full suite reported 2466 passed, 3 skipped and 18 failed. Seven
catalog/count failures were subsequently corrected and retested; two socket
failures passed outside the sandbox. Eight desktop build-fixture failures concern
the pre-existing embedded Beztrace validation changes, and one release-skill
reference still describes Beta 9 while the pre-existing source target is Beta 10.
Those unrelated sources were preserved. The initial report is
`full-suite-initial.md`; the full suite is not claimed green.

Later release follow-up: the desktop fixtures, tool-count assertions and stale
release-skill metadata were corrected for publication. The complete Beta 10
release gate passed 2,492 Python tests and 222 desktop tests. The initial results
above are retained as historical evidence; see
[Beta 10 qualification](../../BETA10-VALIDATION.md).

## Installation state

Build, installation, relaunch and live verification are complete. The installed
version is 2.0.0 Beta 10/build 52. Glyphs and the desktop app are running.
Both disposable test documents were closed after saving and verification;
Hershey Roman Simplex is reopened and active. No font edit or save was issued
against that user document during live qualification; its dirty flag and
generation remained unchanged across those checks.

The installed runtime uses transactional copies, not development symlinks.
The existing receipt names `build/simple-native-scripting`; the lean builder
rebuilt that exact target using the existing `build/private-runtime` inputs.
The installed payload carries the existing source's Beta 10/build 52 metadata.
The scoped `--only mcp` transaction preserved the inspector bundles and retained
its backup at `~/Library/Application Support/Glyphs MCP/lean-v2/transaction-ee2mmaov/backup`.

The desktop app was built with fresh DerivedData, verified against
`dist/local/build-receipt.json`, installed at `/Applications/Glyphs MCP.app`,
verified again and relaunched. Its previous copy is recoverable at
`build/local-install-backups/font-creation-bcf9f87738fa/Glyphs MCP.app`.
See `desktop-installation.json` for the receipt and bundle hash. No release feed,
signed release or global plugin cache was changed.
