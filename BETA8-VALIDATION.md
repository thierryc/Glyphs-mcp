# Beta 8 development preparation

Source target: `2.0.0-beta.8`, desktop build **50**, branch `lit/v2-beta`.
Status: **metadata preparation only; no Beta 8 release build or installation.**

- Advanced `release.json`, app beta identity and both Xcode build configurations
  with the existing version helper, after a dry run.
- Updated current v2 guidance, release reference, metadata assertions and the
  synchronized eleven-skill package. Twelve tools and protocol 1 are unchanged.
- Preserved the signed Beta 7 tag `190d25c5`, its verified private-draft assets
  and evidence in [BETA7-VALIDATION.md](BETA7-VALIDATION.md).
- Beta 7's actual signed-update test is pending a desktop unlock. Its release
  has not been published. Published Beta 6 downloads and signed feed remain
  unchanged; stable Latest and pinned Glyphs 3/v1 documentation are untouched.
- Removed obsolete and unused build outputs (4,229,212,167 bytes in total).
  Retained only current release/test artifacts and signature utilities until
  Beta 7's distribution work is complete.

Metadata, documentation, synchronization and package checks are recorded below.
These checks are not Beta 8 native or signed-release qualification.

## Checks — September 27, 2026

- 30 focused metadata, version-bump, documentation and release-skill tests passed.
- Eleven canonical/packaged skills match; lean package checks pass with twelve
  tools and both runtime architectures.
- Documentation production build and patch-whitespace checks passed.
- The published signed appcast is byte-for-byte unchanged from the Beta 7 tag.
- No Beta 8 tag, application build, installation or publication was performed.
