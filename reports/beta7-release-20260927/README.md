# Beta 7 release qualification — September 27, 2026

Candidate: `2.0.0-beta.7`, desktop build **49**, branch `lit/v2-beta`.

The complete local release gate passed with **2,262 Python tests passed,
one skipped and five warnings**, and **210 macOS tests passed**. It also
verified deterministic payloads, both private runtime architectures, eleven
synchronized skills, twelve public tools, documentation production output,
source metadata and the unsigned desktop application. The full local log has
SHA-256 `598f997eaa7268b862056a29e27bd6accdeaee0e77ecc789e18220fd6d82e3f9`.

Native editing, actual editor saving/restoration, installed Codex text actions,
source/build/installed/loaded identities and the 320-run paired benchmark are
recorded in [the implementation report](../unified-results-20260926/README.md)
and [installed qualification](../unified-results-20260926/installed-20260927/README.md).
Those are development-installation checks, not signed-distribution evidence.

## Known qualification limits

- Installed visual card countdown, progress and Details interaction remain
  unqualified because computer-use access to Codex was rejected. Mock-host
  tests and installed text actions are separate passing evidence.
- Physical Intel, minimum-macOS and the complete manual client matrix remain
  open. Universal compilation and architecture runtime checks do not replace
  these tests.
- The installed report lists live fault-injection cases not repeated on its
  exact loaded identity. It also records the separate unnamed-node null-to-empty
  normalization issue in typed recovery.

Signing, notarization, update acceptance, publication and cleanup evidence is
added after each step completes. No failed security check may be bypassed.

## Signed distribution

Signed tag `v2.0.0-beta.7` identifies candidate commit `190d25c5`. The tag and
beta branch were pushed; stable `main` was not changed. Developer ID signatures,
94 native files, 47 bundles, notarization, stapled tickets, Gatekeeper and
signature-preserving installed copies passed. All four Apple submissions were
accepted; identifiers are in [distribution state](distribution-state.json).

The signed payload passed startup and catalog checks on ARM64 and x86_64,
seven paired typed preparation/recovery cases per format, and 30 native script
execution/restoration checks per format. These isolated tests use a native
fixture save adapter; actual editor Save evidence remains in the earlier
installed qualification report.

The signed disk image layout was written and checked as Finder metadata, using
the same DS_Store procedure as Beta 6. No alternative UI automation was used.
The guarded publisher reran the complete local gate and passed final signed
artifact verification before completing and verifying the four-asset draft upload.

The older-build update fixture is signed, notarized and ready. The Mac locked
before VM setup; signed-update acceptance and public publication are pending.
The exact signed feed has not replaced the published Beta 6 feed.

## Cleanup so far

Thirty obsolete build directories were removed, totaling 2,140,310,223 bytes
(sum of file sizes; not a physical-space measurement). Historical build
evidence was retained in the excluded local release archive. The current
release/update fixture and dependencies remain until distribution is complete.
The installed runtime is copied independently; fresh status showed no open
fonts or active jobs. Dactylotype and installed plugin caches were untouched.
Beta 8/build 50 metadata changes are applied separately; they do not change
the frozen Beta 7 tag or distribution assets.

A second cleanup removed 97 unused outputs and dependency caches.
Total removed file sizes across both passes: **4,229,212,167 bytes**. Only the
current `dist/` release assets, `build/desktop-dependencies` signature utilities
and `build/update-trial-beta7-20260927` fixture remain pending distribution.
Website build output and generated documentation caches were also removed.
