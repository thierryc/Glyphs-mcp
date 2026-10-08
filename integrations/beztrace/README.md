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
preservation and fresh-panel tracing without Choose Engine passed. Public assets
and supported-platform qualification remain required before managed setup can be
enabled. This evidence applies to the persistent-engine overlay, including its
bundle-derived About label, and the exact signed build tested locally.

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
