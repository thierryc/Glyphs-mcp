# Beta 11 release — September 30, 2026

Release `2.0.0-beta.11`, desktop build 53, on `lit/v2-beta`.
The user authorized publication of this beta. Local-only routing instructions
remain excluded. Scope is release metadata and current guidance; native/runtime
behavior is inherited unchanged from Beta 10.

See [qualification](../../BETA11-VALIDATION.md) for scope, historical native
evidence and remaining manual acceptance limits. The complete local gate passed: 2,492 Python tests (two skips, five warnings),
222 desktop tests, deterministic payloads, both private runtimes, documentation
and package checks. See `python-tests.md`. Developer ID signing verified 94 native binaries and 47 bundles, plus the
separately bundled engine; see `signed-engine.json`. Both signed private runtimes
passed startup and packaged catalog/resource checks; see `signed-runtimes.json`.
Their bytes match the final stapled payload. All three Apple submissions are
accepted; IDs are in `distribution-state.json`. App and DMG tickets and Gatekeeper
acceptance passed. Sparkle archive/feed signatures verify. The guarded publisher
and public-download checks are pending.
