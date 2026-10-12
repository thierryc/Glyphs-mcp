# Next evolution of Glyphs MCP

The baseline is published **2.0.4/build 61**, with twenty tools and eleven managed skills. [Release qualification](../../V2.0.4-RELEASE.md) and [publication evidence](../../reports/2.0.4-build61-published.md) describe what was tested. New source documentation and optional development material do not alter the signed release or its tag.

## Follow-up priorities

1. **Installation evidence from affected Macs.** Use the new logs to distinguish the chosen Glyphs application, its preference domain, missing configuration, a discovered default module and a failed framework load. The reported user's Mac has not been reproduced directly; a missing saved preference is a demonstrated failure mechanism, not proof of every external failure.
2. **Application discovery and Python compatibility.** Keep focused tests for renamed/duplicate Glyphs copies, distinct bundle identifiers, explicit stale preferences, official module defaults, python.org frameworks and no usable Python. Test a signed fresh install on a second real Mac before claiming wider compatibility.
3. **Export qualification.** Preserve native font compilation and private-runtime table/shaping verification. Extend the signed default-Python VM gate to variable-font exports and failure/recovery scenarios; the new build-61 gate covers six static combinations.
4. **Platform coverage.** Qualify a physical Intel Mac and exact macOS 14.0, or revise support claims with evidence. Rosetta startup is a separate result.
5. **Setup usability.** Observe installation with more than one Glyphs copy and a genuine Python failure. Check whether the scoped readiness warning, detected paths, copy selection and Install anyway wording let a user recover without support.

These are proposed directions, not new implemented features. Keep each change reviewable and test its actual behavior. Do not expand the public tool surface or package optional dependencies solely to simplify an internal implementation.

## Contributor handoff

Production code is in `src/sidecar`, `src/bridge`, `src/protocol` and `src/companions`; desktop setup is in `macos-installer`. Managed skills remain in `skills/` and are synchronized into the agent package. Optional macro iteration is preserved in `extras/`, outside the signed skill inventory. Historical qualification probes retain their original paths and versions.

Use [CODEX.md](../../CODEX.md) for build and validation instructions. Begin a new branch from main; keep release tags immutable. Preserve linked development payloads and runtime inputs when cleaning generated outputs. There is no need to reinstall or reset a user's settings for an ordinary upgrade.
