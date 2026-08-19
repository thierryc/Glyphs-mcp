# Glyphs MCP 2.0 runtime

This is the isolated, unreleased Glyphs MCP 2.0 package. It is based on signed
release `v1.11.0` but does not change the shipped 1.x wire contracts.

The catalog contains 27 operations across:

- stable document status and bounded glyph, instance, kerning, audit, and operation pages;
- compatibility, metrics, anchors, spacing, kerning, and export reviews;
- direct apply-first typed mutations through detached simulation and one shared
  verified transaction kernel;
- schema-v3 identity-aware glyph, instance, feature, class, and prefix
  membership/order patches with conflict-aware semantic revert;
- staged, destination-fingerprint-bound source-bundle publication;
- `execute_python` staged-document and live-open-world modes;
- fingerprint-bound `rollback_python_execution` and separate recovery copies.
- content-addressed unsaved-session action commits, bounded change discovery,
  conflict-aware `revert_change`, a passive Change Log, and a drawing-only diff
  Reporter that fills the live geometric band from the pre-agent baseline.

All result envelopes carry request, run, and operation IDs, typed effect and
status, timestamps, warnings/errors, optional page metadata, fingerprints, and
audit receipts. Pages default to 100 items, cap at 500, and are also bounded by
serialized size.

The five enforced layers are contracts, application services, ports, native
adapters, and catalog-driven transport. Core and application modules do not
import GlyphsApp, AppKit, Foundation, FastMCP, or Uvicorn. Native Glyphs objects
remain inside the main-thread adapter.

Typed mutation tools take `documentId`, `expectedDocumentFingerprint`, explicit
items, and an optional reason. They allocate one operation ID, simulate the
writable patch on `GSFont.copy()`, capture every derived effect, apply once to
the live font, and verify the complete observed result. Preparation tools and
typed apply tokens are intentionally absent. Confirmation remains only for
Python and export/open-world effects.

Ordered canonical collections remain ordinary detached JSON lists, but schema
v3 addresses their entities by stable IDs and represents order independently.
`apply_glyph_updates`, `apply_opentype_updates`, and
`apply_instance_updates` all use that one semantic collection abstraction.
Master duplication, layer membership changes, and staged-Python structural
replay remain explicit later boundaries.

## Worktree-contained development

From the repository root:

```bash
python3.12 -m pytest -q src/glyphs-mcp/tests
python3.12 scripts/build_v2_runtime_payload.py
git diff --check
```

The builder writes only to `build/v2-runtime/`. It does not install, link,
reload, or execute the plug-in in Glyphs. This correctness milestone runs live
gates only in Glyphs 4 with disposable copies and never the production source;
Glyphs 3.5 remains on signed v1.11 and is covered by source-level adapter tests.

Inside each supported host, `glyphs_mcp_v2.live_gates.verify_copy_and_make_copy`
accepts only a font whose family name starts with `Glyphs MCP V2 Disposable`.
It verifies canonical and serialized clone equality plus `save(makeCopy=True)`
path/dirty-state invariants, writing only to a new explicit output path.
