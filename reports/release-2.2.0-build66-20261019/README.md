# 2.2.0 / build 66 preparation — 19 October 2026

The universal candidate is signed, notarized and stapled. The final DMG and app
ZIPs, both Sparkle signatures, Gatekeeper acceptance and installed-copy
identities passed `verify_release_artifacts.sh --tag v2.2.0 --write-checksums`.
`qualification.json` records the exact distribution hashes, accepted Apple
submissions and final packaged-runtime results. The full gate passed 3,143 Python
tests (two skips), 298 desktop tests, documentation and deterministic packaging.

The exact signed ZIP was tested in VirtualBuddy. Manual app replacement from
2.0.2/build 57 preserved the older manager; the production installer migrated
MCP and both installed inspectors to 2.2.0/build 66 with transaction backups.
The new companion showed the expected Tasks update requirement with the old
sidecar before migration. See the two VM receipts for their exact scope.

The companion Setup page remained in a Python-check state during inspection.
Its UI acceptance is unresolved despite the successful CLI native preflight.
This preparation does not establish an actual Sparkle-delivered replacement,
loaded native recovery/header/archival/retention acceptance or public release.
The published 2.1.0 feed remains unchanged. Physical Intel hardware is unavailable;
x86_64 runtime execution was tested through Rosetta. The host working Glyphs
session and development installation were not changed or restarted.

Detailed build, Apple submission, signing and verification logs remain local in
`build/release-2.2.0-build66-final/`; the full gate log and frozen source inputs
are in `build/release-test-run.oPWbLG/`. Only qualification notes and these
receipts were added after the distribution was built.
