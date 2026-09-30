# Beta 10 release candidate — September 30, 2026

Release `2.0.0-beta.10`, desktop build 52, on `lit/v2-beta`.
The user authorized committing all publishable changes and publishing this beta.
Local-only routing instructions remain excluded.

See [qualification](../../BETA10-VALIDATION.md) for scope, completed native checks
and unperformed acceptance checks. The complete local gate passed:
2,492 Python tests (two skips, five warnings), 222 desktop tests, deterministic
payloads, both private runtimes, the website build and source/package checks.
See `python-tests.md`. The initial gate found one remaining twelve-tool Swift
assertion; it was corrected and the complete gate rerun successfully.

Developer ID signing verified 94 native binaries and 47 bundles. The separately
bundled universal Beztrace engine is signed and its refreshed release-copy
checksums verified; see `signed-engine.json`.
Apple accepted the expanded payload submission and all three native plugin
tickets were stapled and verified. Both signed private runtimes passed startup,
HTTP/stdio catalogs, packaged installer CLI and MCP App resource/response checks;
see `signed-runtimes.json`. App and DMG notarization passed. All three Apple submissions were accepted;
submission IDs are in `distribution-state.json`. Stapling, Gatekeeper acceptance,
nested signatures, signature-preserving installation copies, extracted ZIP and
checksums passed. Sparkle archive/feed signatures verified.
Publication and public download verification are pending.
