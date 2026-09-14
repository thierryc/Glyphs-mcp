# Beta 1 repository consolidation — September 14, 2026

Scope: commit and clean the current `lit/v2-beta` worktree in
`build/milestone7/desktop`, as explicitly selected by the user. Gap 7 was already
committed in `e572d5df`; this consolidation records the remaining desktop,
installer, release tooling, documentation migration and historical qualification
files. The older parent checkout is outside this cleanup; its benchmark fixtures
remain available to the current native qualification scripts.

## Review and correction

The pending changes were inventoried before staging: 101 tracked-file changes
and 407 untracked files. The new files include desktop project/template code,
tests, pinned resource provenance, historical discovery evidence and the frozen
v1 documentation snapshot. The large images belong to that documentation snapshot;
generated build directories and installed runtime files remain outside the commit.

The first complete local gate reached Python validation and reported **1,911
passed, three failed and two skipped**. All three failures were real FastMCP
transport tests encountering a module stub left in `sys.modules` by earlier
resource tests. Four resource test classes now scope their module dictionary,
environment and import path with standard `unittest.mock` cleanup. This changes
test isolation, not the Glyphs 3 or Glyphs 4 runtime. The ordered focused rerun
passed all 20 cases, including the previously failing HTTP and width requests.

Staging also exposed PDF cross-reference whitespace, exact vendor/license text,
Markdown hard breaks in the frozen v1 snapshot and one extra blank line at the
end of a Swift source file. `.gitattributes` now treats PDFs as binary and
exempts the pinned text/snapshot from whitespace rewriting. Their bytes and
checksums are preserved. Only the extra source-file blank line was removed.

## Validation

**The complete local release gate passed after the isolation correction.**

| Check | Result |
|---|---|
| Full Python suite, including fresh Python 3.12/3.14 dependency environments | **1,914 passed, 2 skipped**, 94.78 seconds |
| macOS installer/desktop suite | **179 passed, zero failures**, 13.95 seconds |
| Ordered resource/real-transport regression | **20 passed** |
| Deterministic payloads, both private runtime architectures, HTTP and stdio catalogs | Passed |
| Eleven managed skills, source versions, frozen v1 docs and documentation build | Passed |
| Unsigned Debug app build, bundle/payload verification and candidate validation | Passed |
| Staged source whitespace | Passed; exact vendor/frozen text is preserved through attributes |

The two optional skips were unavailable GitHub Copilot CLI and the real AppKit
drawing test requiring an opted-in application context. Neither is reported as
passed. Dependency deprecation warnings remain in the log. No test assertions
were relaxed or failing tests skipped to obtain the passing result.

Evidence: [final complete log](local-release-tests.log.gz),
[first failure log](local-release-tests-first.log.gz),
[focused rerun](test-isolation-focused.log), and [structured facts](facts.json).
The local gate built an unsigned candidate and reported `publishable:false`.
This was not a new signed release, installation or native font benchmark.

The rebuilt candidate still has the step-7 runtime fingerprints:

- Bridge: `sha256:77bec730360ce043f184dcdc958fbad5519c7858fc06994bad292abf4ea01138`.
- Sidecar: `sha256:0d1590b10c67cd7eebbc4d3ea93f5f91eec51d9e80285f2d8b65d0c4398450a3`.

The frozen `legacy/glyphs3` tree has no changes. No installed application or font was
changed during this consolidation. Existing native qualifications remain in
their original reports; passing local automated checks does not replace native evidence
or imply release readiness. Gap 8 remains paused.
