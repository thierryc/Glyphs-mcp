# Beta 8 development preparation

Source target: `2.0.0-beta.8`, desktop build **50**, branch `lit/v2-beta`.
Status: **metadata preparation only; no Beta 8 release build or installation.**

- Advanced `release.json`, app beta identity and both Xcode build configurations
  with the existing version helper, after a dry run.
- Updated current v2 guidance, release reference, metadata assertions and the
  synchronized eleven-skill package. Twelve tools and protocol 1 are unchanged.
- Preserved the signed Beta 7 tag `190d25c5`, its verified published assets
  and evidence in [BETA7-VALIDATION.md](BETA7-VALIDATION.md).
- Beta 7 is published with verified public downloads and its exact signed beta
  feed. Its signed-update/component-migration test remains unperformed and is
  disclosed in the release notes. Stable Latest and pinned Glyphs 3/v1
  documentation are untouched.
- Removed all generated repository builds after Beta 7 public verification,
  including release/test artifacts and signature utilities. Three cleanup
  passes removed 5,725,506,914 bytes by logical file size; this is not a
  physical-space measurement. Source worktrees and installed runtimes remain.
- Publication follow-up: 30 focused tests, eleven-skill synchronization and the
  documentation production build passed before generated output was removed.

Metadata, documentation, synchronization and package checks are recorded below.
These checks are not Beta 8 native or signed-release qualification.

## Checks — September 27, 2026

- 30 focused metadata, version-bump, documentation and release-skill tests passed.
- Eleven canonical/packaged skills match; lean package checks pass with twelve
  tools and both runtime architectures.
- Documentation production build and patch-whitespace checks passed.
- Before publication, the signed appcast was unchanged from the Beta 7 tag.
  After public download verification, it was replaced by the exact signed
  Beta 7 release appcast; no Beta 8 feed item was generated.
- No Beta 8 tag, application build, installation or publication was performed.
