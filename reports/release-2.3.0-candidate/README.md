# 2.3.0/build 68 — published qualification

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

## Native upgrade acceptance

After restarting the macOS 14.6.1 VM, evidence reads and guest input worked.
The exact signed 2.2.0/build 67 app upgraded through its standard signed updater
to 2.3.0/build 68. The upgraded application tree matches the verified reference
exactly, strict signature verification passed, and component receipts remained
unchanged until the explicit MCP card Update.

The server-update reminder appeared with the intended headline and readable
text. Open Setup navigated without installing components. The MCP card showed
Update available and a filled primary Update button; both unchanged inspectors
showed Installed and secondary Update buttons. The existing Glyphs-running
safeguard disabled writes until the guest Glyphs app was explicitly quit.
The MCP-only update then passed, its receipt reports 2.3.0, and its card returned
to Installed with secondary Update styling. Inspector versions remained unchanged.
Diffenator is absent; independent Beztrace is preserved and the older-macOS
requirement is visible. See [native evidence](vm-upgrade/acceptance.json).

Later, once-per-version/location, quiet login, unknown/newer/development-linked
installations and failure/cancellation policy branches are covered by desktop
tests; this report does not claim a manual VM replay of every branch. VirtualBuddy
does not expose guest accessibility elements, so prior live accessibility limits
remain. The working host Glyphs session and component installation were untouched.

The release is published and all six assets passed anonymous download verification.
The exact VM-qualified archive was preserved after repacking altered only ZIP
access-time metadata; complete artifact security checks passed again.
See [public downloads](public-downloads.json). Diffenator has no distributable
runtime in this release.
