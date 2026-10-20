# 2.3.0/build 68 — signed candidate, not published

Diffenator is deferred beyond this release and removed from Setup. Its future
maintained fork must pass fresh dependency/license, comparison, signing,
notarization and supported-macOS qualification.

The candidate includes clear server/plugin update reminders, visible primary
Update actions, stable inspector comparison after strict ownership/signature
verification, and managed Beztrace engine 0.2.1 / companion 0.2.0 build 25.
Beztrace remains Apple Silicon/macOS 26.6.2 or later with manual engine selection;
independent or modified installations, shared engines and user settings are protected.

The revised scope passed 3,155 Python tests (two skipped), 304 desktop tests,
documentation, deterministic payload and package consistency checks. Subsequent
localized-card fixes passed 33 focused desktop and 51 focused Python tests.
Localized card states and Details were rendered and reviewed in English, French
and Chinese in light/dark appearance. ImageRenderer does not render native link
controls; their live accessibility/keyboard check remains separate.

All three final notarizations (payload, app, DMG) were accepted and stapled.
Complete artifact verification passed, including both app archives, exact payload
identities, Developer ID/team, hardened runtime, Gatekeeper and update signatures.
Both exact signed private runtimes passed HTTP/stdio/package checks; Intel
execution used Rosetta, not physical hardware. The exact Beztrace public plugin
passed anonymous checksum/inventory/trust checks. Its managed lifecycle passed
in a disposable home, preserving modified content, settings and shared engines.

## Remaining native gate

The macOS 14.6.1 VM baseline was signed desktop 2.2.0/build 67 with matching
components. The exact 2.3.0 archive passed guest Gatekeeper and the standard
updater displayed the new-version prompt. Component receipts were unchanged at
that point. The observer then hit an input/output error while reading evidence;
upgrade completion and reminder behavior are not claimed. A bounded diagnostic
probe is prepared and awaiting the requested human Terminal handoff.

No 2.3.0 GitHub release, optional Diffenator asset or desktop feed advancement
has occurred. The host working Glyphs session and component installation were
not changed. Publication remains blocked by the native acceptance gate.
