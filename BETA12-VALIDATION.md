# Beta 12 preparation — build 54

> Historical Beta guidance: the local checkout now prepares unpublished
> 2.0.0/build 55. Beta 12/build 54 evidence remains preserved; the public
> download and signed Beta feed still target Beta 11/build 53. See the
> [current release checklist](V2-RELEASE-CHECKLIST.md).

Date: 2026-09-30. Branch: `lit/v2-beta`.
Product: `2.0.0`; release: `2.0.0-beta.12`.

**Current status, 5 October 2026:** unpublished local candidate. The sections
below record the original 30 September metadata-only preparation. Subsequent
authorized fixes produced unsigned Debug builds, VM installations and scoped
native qualification. They do not qualify a signed public Beta 12 distribution.
See [current milestone evidence](V2-RELEASE-CHECKLIST.md) and the follow-up below.

## Scope

Prepare Beta 12 metadata from published Beta 11/build 53. Update the release
configuration, desktop beta number/build, current documentation, release skill
reference and existing identity test. Product version remains `2.0.0`, bridge
protocol and interface revision remain `1`, with thirteen public tools and
eleven managed skills. No runtime or native font behavior changes in this step.
Glyphs 4 remains the target; Glyphs 3 support is not introduced by this bump.

## Preparation checks

Passed on 2026-09-30 with Python 3.14.6:

- 45 focused tests across `test_beta_release.py`, `test_simple_v2_identity.py`,
  `test_simple_v2_build.py`, `test_docs_versioning.py`, `test_bump_version.py`
  and `test_docs_surface_sync.py`.
- `desktop_release_identity.py`: Beta 12/build 54 on the beta channel.
- `check_lean_package.py`: thirteen public tools, eleven skills, both runtime
  architectures.
- `sync_codex_plugin_skills.sh --check`: all eleven packaged skills synchronized.
- `npm run build --prefix website`: production documentation build passed.
- `git diff --check`: passed.

An initial test invocation named a nonexistent `test_skill_sync.py` and collected
no tests; the corrected invocations above passed. Skill synchronization was
verified with the repository's dedicated checker. Temporary test payloads are
not desktop distribution builds.

## Original preparation boundary — 30 September

The full release suite, desktop build, native acceptance, Developer ID signing,
notarization, signed-update/component-migration acceptance and public download
verification have not been performed for Beta 12. Historical results are in
[Beta 11 qualification](BETA11-VALIDATION.md); they are not Beta 12 acceptance.
Carry forward its physical Intel/minimum-macOS, visual and native UI limitations
until fresh evidence resolves them.

## Distribution

No Beta 12 artifact is built or published by this preparation. Future assets use
`Glyphs-MCP-2.0.0-beta.12.dmg` and `Glyphs-MCP-2.0.0-beta.12.zip`, with future tag
`v2.0.0-beta.12` as a non-Latest prerelease. Published Beta 11 assets, qualification
records and the exact signed `appcast.xml` remain unchanged. Stable Latest remains
v1.11.1. No commit, tag, push, installation or runtime restart is part of this step.

## Authorized local follow-ups — 1–4 October

Local Beta 12 fixes and qualified candidate builds are recorded independently
in [the v2 checklist](V2-RELEASE-CHECKLIST.md): group-pair Undo routing, guided
official Python setup, setup/recovery, Claude card layouts, scripts/saving,
desktop Welcome, localization, keyboard navigation and quiet login. M2 is
complete for the recorded local candidate scope; no full signed release suite
or final distribution acceptance is inferred from these focused results.

Full VoiceOver, visual Reduce Motion and other human checks are
[deferred to the maintainer](V2-MANUAL-TESTS-TODO.md); Intel is also deferred.
Minimum macOS 14.0, stable Beztrace distribution/integration, exact signed
upgrades and final artifact/site acceptance remain separate pending gates.
Published Beta 11 assets and signed feed bytes remain unchanged.

## Stable engine integration — 5 October

Public Beztrace 0.1.1 assets now pass the independent input audit and replace
dev.4 in the local source. Original public metadata/SBOMs/licenses and exact
archive provenance are retained; the old distribution is preserved in staging.
Signing/verifier logic and current setup guidance follow the stable engine
while leaving the independent build-12 plugin native-unqualified.
See [current integration evidence](reports/v2-release-readiness/beztrace-stable-011/report.md).
The earlier missing-release finding is resolved for the engine. Native tracing,
independent companion acceptance and final signed MCP qualification remain open.
