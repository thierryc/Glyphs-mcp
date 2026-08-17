# Glyphs MCP 2.0 runtime

This is the isolated, unreleased Glyphs MCP 2.0 package. It is based on signed
release `v1.11.0` but does not change the shipped 1.x wire contracts.

The catalog contains 30 operations across:

- stable document status and bounded glyph, instance, kerning, audit, and operation pages;
- compatibility, metrics, anchors, spacing, kerning, and export reviews;
- one-time reviewed batch applies through a shared verified transaction kernel;
- staged, destination-fingerprint-bound source-bundle publication;
- `execute_python` staged-document and live-open-world modes;
- fingerprint-bound `rollback_python_execution` and separate recovery copies.
- content-addressed unsaved-session action commits, bounded change discovery,
  conflict-aware `revert_change`, a passive Change Log, and a drawing-only diff
  Reporter.

All result envelopes carry request, run, and operation IDs, typed effect and
status, timestamps, warnings/errors, optional page metadata, fingerprints, and
audit receipts. Pages default to 100 items, cap at 500, and are also bounded by
serialized size.

The five enforced layers are contracts, application services, ports, native
adapters, and catalog-driven transport. Core and application modules do not
import GlyphsApp, AppKit, Foundation, FastMCP, or Uvicorn. Native Glyphs objects
remain inside the main-thread adapter.

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
It verifies canonical and serialized clone equality plus `save(makeCopy=True)`
path/dirty-state invariants, writing only to a new explicit output path.
