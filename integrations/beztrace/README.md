# Persistent Beztrace engine handoff — release dependency

This overlay targets companion source dbd7a696afda9a215c8e8a4aa42315cd799116f9
(build 15). SOURCE.json binds its original files. It changes no separate checkout,
installed plugin or font. The patched source has passed Python syntax validation.

`scripts/build_beztrace_companion.py` applies this overlay to a verified disposable
source export and prepares independently numbered **0.1.0 build 16**, preserving
the upstream package schema, licenses and SDK loader provenance. Its local
package has passed inventory validation, Developer ID signing, Apple notarization
and stapled-ticket validation. On macOS 26.7.1 arm64 with Glyphs 4.1.1/build 4108,
its loaded About identity, first trace, exact Undo/Redo, original contour/width
preservation and fresh-panel tracing without Choose Engine passed. Managed setup is qualified for Apple Silicon on macOS 26.6.2 or later;
macOS 14 and Intel execution remain unqualified. This evidence applies to the persistent-engine overlay, including its
bundle-derived About label, and the exact signed build tested locally.

The exact signed build-16 ZIP is now hosted alongside Glyphs MCP v2.0.2:
[download build 16](https://github.com/thierryc/Glyphs-mcp/releases/download/v2.0.2/beztrace-glyphs-0.1.0-build16-macos-universal.zip).
It is 123,623 bytes, SHA-256
`b94bbe4f4d39d023bac90a22a6850e2ef6b49429164473982af202630186d10f`.
The actual public download passed inventory, Developer ID and Gatekeeper
notarization verification, then install/update/remove/reinstall in an isolated
home on macOS 26.7.1 arm64. Explicit user engine selection and unrelated settings
were preserved throughout. The same public archive passed all four operations
in a clean macOS 26.6.2 arm64 VM; the maintainer supplied its complete passing
result. [Qualification evidence](qualification-build16.json) records the exact
archive and supported scope. The production source catalog now enables arm64
on macOS 26.6.2 or later and rejects unqualified platforms before downloading.
This does not change the catalog embedded in the already published desktop app;
shipping that catalog requires a new desktop build.

Apply persistent-engine.patch in a disposable checkout of that exact revision;
copy engine_settings.py into the plugin's beztrace_companion directory. Assign a
new companion build through its packaging workflow. Existing build 15 signatures,
manifests and native qualification do not apply to modified code.

Contract: ~/Library/Application Support/beztrace/engine-settings-v1.json contains
schemaVersion: 1, optional userEngine, and optional managedEngine (absolute paths).
User selection has priority, survives panel reopen and remains intact during
managed setup changes. Invalid or missing overrides must not silently fall back.
Glyphs MCP provisions the verified bundled 0.1.1 engine in
~/Library/Application Support/beztrace/engines/0.1.1/bin/beztrace. The companion
continues to work independently of the MCP service.

Release gates: validate the patched plugin, assign accurate provenance, sign and
notarize independently, qualify fresh-panel Trace/Done/Undo/Redo, then populate
the optional catalog with exact asset URLs, sizes, inventories and trust subjects.
Until then managed setup is unavailable and independent installations are preserved.
