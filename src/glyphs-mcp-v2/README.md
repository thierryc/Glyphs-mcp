# Glyphs MCP 2.0 runtime

This is the isolated, unreleased Glyphs MCP 2.0 package. It is based on signed
release `v1.11.0` but does not change the shipped 1.x wire contracts.

The catalog contains 29 operations across:

- stable document status and bounded glyph, instance, kerning, audit, and operation pages;
- compatibility, metrics, anchors, spacing, kerning, and export reviews;
- direct apply-first typed mutations through detached simulation and one shared
  verified transaction kernel;
- schema-v4 identity-aware glyph, layer, master, instance, feature, class, and
  prefix membership/order patches with conflict-aware semantic revert;
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
writable patch on `GSFont.copy()`, capture every canonical effect, apply once to
the live font, and verify the complete observed result. Preparation tools and
typed apply tokens are intentionally absent. Confirmation remains only for
Python and export/open-world effects.

The canonical layer tree stores authoritative state: outline/component
geometry, anchors, advance width, metrics keys, and layer identity/state.
Glyphs' `LSB` and `RSB` getters are intentionally not canonical leaves because
they are projections of geometry, width, metrics inheritance, and master
italic state, while assigning them is a command that moves geometry or changes
width. Excluding those volatile projections prevents impossible replay targets
and avoids two native getter calls per captured layer. Spacing may still be
expressed and inspected as sidebearings at the workflow boundary; verification
records the authoritative geometry and width effects caused by that command.

Ordered canonical collections remain ordinary detached JSON lists, but schema
v4 addresses their entities by stable IDs and represents order independently.
`apply_glyph_updates`, `apply_opentype_updates`, and
`apply_instance_updates` use that one semantic collection abstraction.
`apply_master_updates` extends it to a composite master, its owned glyph layers,
and its kerning partition. Arbitrary special/intermediate layer membership and
staged-Python structural replay remain explicit later boundaries.

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

## Glyphs 4 schema-v3 qualification

After the current v2 source bundle is explicitly linked and Glyphs 4 is
restarted, open a disposable font whose family name starts with
`Glyphs MCP V2 Disposable`. The Macro window can then run:

```python
from GlyphsApp import Glyphs
from glyphs_mcp_v2.live_gates import verify_schema_v3_structural_kernel

print(verify_schema_v3_structural_kernel(Glyphs.font))
```

The gate calls only the existing public apply-first tools and generic
`revert_change`. It qualifies glyph, OpenType, and instance membership,
updates, order, deletion, selective revert, stale fingerprints, and invalid
duplicates through 22 one-transaction operations. It never saves. Every
successful forward operation is tracked so an unexpected failure first tries
to revert the remaining operations in reverse order; the gate refuses to
report success unless the exact baseline fingerprint, path, active master, and
reported dirty state are restored.

## Glyphs 4 schema-v4 master qualification

After rebuilding, relinking, and restarting Glyphs 4, the same disposable font
can run the separate master lifecycle gate:

```python
from GlyphsApp import Glyphs
from glyphs_mcp_v2.live_gates import verify_schema_v4_master_lifecycle

print(verify_schema_v4_master_lifecycle(Glyphs.font))
```

The gate duplicates one existing master, preserves its native master and layer
payload, updates and reorders it, deletes it, and reverts all four operations
in reverse order. It also verifies stale-fingerprint and duplicate-ID atomic
refusals. It never saves and reports success only after exact canonical
baseline, active-master, path, and dirty-state restoration.
