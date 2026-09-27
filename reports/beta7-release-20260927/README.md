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
