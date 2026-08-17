# Glyphs MCP 2.0 runtime

This is the isolated, unreleased Glyphs MCP 2.0 package. It is based on signed
release `v1.11.0` but does not change the shipped 1.x wire contracts.

The compact catalog contains 24 operations across:

- stable document status and bounded glyph, instance, kerning, audit, and operation pages;
- read-only compatibility, metrics, anchors, spacing, kerning, and export analysis;
- direct fingerprint-bound batch applies through a shared verified transaction kernel;
- direct, fingerprint-bound `rollback_change_operation` for typed mutations;
- staged, destination-fingerprint-bound source-bundle publication;
- `execute_python` staged-document and live-open-world modes;
- fingerprint-bound `rollback_python_execution` and separate recovery copies.

All result envelopes carry request, run, and operation IDs, typed effect and
status, timestamps, warnings/errors, optional page metadata, fingerprints, and
audit receipts. Pages default to 100 items, cap at 500, and are also bounded by
serialized size.

The five enforced layers are contracts, application services, ports, native
adapters, and catalog-driven transport. Core and application modules do not
import GlyphsApp, AppKit, Foundation, FastMCP, or Uvicorn. Native Glyphs objects
remain inside the main-thread adapter.

## Apply-first change review

Typed document mutations apply immediately after fingerprint prevalidation and
publish one canonical `ChangeOperation`. The same operation ID identifies the
response, audit receipt, paginated semantic details, Changes panel row, Edit
View overlay, and rollback metadata.

Typed rollback uses that same operation ID and stored inverse patch. It refuses
stale documents, applies once through the transaction kernel, updates the panel
and Reporter state immediately, emits one audit receipt, and never saves.

The v2 bundle replaces the Candidate Reporter with the drawing-only **Glyphs
MCP Changes** Reporter and connects the existing Changes menu to the isolated
v2 operation store. Double-clicking a row or choosing **Open Changed Glyphs**
reuses one tagged Edit tab per document. There are no Font View marks and no
persistent candidate layers or review metadata.

The removed preparation names `review_glyph_updates`,
`review_anchor_updates`, `review_kerning_updates`, `review_metrics_updates`,
and `review_compatibility_updates` are documentation tombstones only. They are
not registered aliases. Export and Python execution retain exact confirmation
because those confirmations enforce safety boundaries rather than visual
acceptance.

## Worktree-contained development

From the repository root:

```bash
python3.12 -m pytest -q src/glyphs-mcp/tests
python3.12 scripts/build_v2_runtime_payload.py
git diff --check
```

The builder writes only to `build/v2-runtime/`. It does not install, link,
reload, or execute the plug-in in Glyphs. Live gates require disposable copies
on Glyphs 3.5 and 4 and must not use the production source.

Inside each supported host, `glyphs_mcp_v2.live_gates.verify_copy_and_make_copy`
accepts only a font whose family name starts with `Glyphs MCP V2 Disposable`.
It verifies canonical equality with the live font, deterministic serialized
equality between two independent detached clones, and `save(makeCopy=True)`
path/dirty-state invariants, writing only to a new explicit output path. The
serialized archive is not compared directly with the live font: Glyphs 4
intentionally omits presentation state such as open Edit tabs from
`GSFont.copy()`, and that state is outside the staged mutation model.
