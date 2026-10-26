# 2.3.1/build 69 publication evidence

PR #65 merged the opt-in development-skill checkbox and positive connection
setup guidance onto published 2.3.0. The signed tag includes the subsequent
release-documentation link correction. The first gate stopped at that broken
link before signing or uploading any artifacts; the complete corrected gate
passed 3,155 Python tests (two skipped), 305 desktop tests, documentation,
deterministic payloads, runtime startup and package checks.

Apple accepted the expanded payload, final app and disk image. All tickets,
Developer ID signatures, hardened runtime, timestamps, Gatekeeper checks,
component identities and signed update archive/feed checks passed. Both exact
signed private runtimes passed HTTP/stdio and packaged CLI checks. The final
mounted disk-image layout was visually inspected before upload. All six release
assets then passed anonymous public-download and checksum verification.

The application was not installed locally. Native font behavior and updater
implementation did not change; the prior 2.3.0 native/VM evidence retains its
original scope. No fresh end-to-end GUI updater/VM run was performed. Physical
Intel hardware remains unavailable; x86_64 execution used Rosetta.

See the adjacent JSON records and SHA256SUMS for artifact identities. The feed
promotion copies the exact signed and publicly verified appcast bytes.
