# Curve Inspector — Inspect & Repair

Research and implementation plan for adding **Inspect & Repair** to the existing
**Curve Inspector** plugin, with a shared geometry engine and an accompanying
agent skill.

**Status: 0.5.1 signed, notarized and installed locally; safe native relaunch pending.**
The 0.3.0 proposal-controller records are historical and do not qualify the new
human workflow. See the [companion README](../../README.md) and
[qualification status](../../qualification/candidate-status.json).

**Organization:** keep Curve Inspector in the existing Glyphs MCP repository at
`src/companions/curve-inspector/`. These repair documents live alongside it in
`docs/repair/`. The existing plugin, build scripts and regression tests retain
their locations. There is no separate Curve Inspector or repair repository in
the active checkout, and no duplicate plugin source.

## Recommended product

Keep one Curve Inspector installation and its existing identities:

- Plugin name: **Curve Inspector**; description: **Inspect & Repair**.
- Bundle identifier: `com.ap.cx.glyphs-curve-inspector`.
- MCP companion identifier: `curve-inspector`.
- Human workflow: select → choose Star or Default node → Apply. No preview mode.
- Fixed 280 × 146-point panel, always-visible Max change field and All masters.
- Star: only broken joins; healthy ordinary nodes and existing stars are no-ops.
- Default node: materialize detached native star geometry, including existing stars.
- Internal Tunni: retain only when continuity, neighbors and Max change pass.
- Both modes: continuous effective-outline bound, default `0.001 × UPM` units.

See the [companion README](../../README.md) for automatic scope, atomic master
acceptance, guarded application, Undo and unsupported expansion cases. Native
star movement is measured independently of stored-coordinate preservation.
Agent proposal interfaces below retain their explicit method and coverage rules.

The reusable engine is a separate Python module inside this companion. Future
builds bundle the same pinned engine revision into the plugin
and skill helpers; neither depends on a developer checkout at runtime. The
Reporter remains a cached visualization component. Repair remains available
when its overlay is disabled.

## Documents

| Document | Purpose |
| --- | --- |
| [PLAN.md](PLAN.md) | Architecture, deliverables, milestones, gates and deferred work |
| [Algorithm](algorithm.md) | Continuity mathematics, candidate construction and acceptance |
| [Plugin API](plugin-api.md) | Current V2 scripting route and proposed shared extension |
| [Verification](verification.md) | Geometry fixtures, native qualification and master coverage |
| [Skill design](skill.md) | Planned agent workflow, examples and recovery rules |
| [Sources and licenses](sources-and-licenses.md) | Inspected implementations, pinned revisions and reuse boundaries |

## Evidence labels

The documents distinguish:

- **Researched fact:** supported by inspected source or an identified primary
  reference. Documentation of intended native behavior is not a local host test.
- **Proposed choice:** a requirement or design to implement and qualify later.
- **Unverified assumption / gate:** an unanswered question that may prevent a
  method from being enabled.

Finite interpolation checks provide sampled evidence. They do not prove
continuity everywhere in the designspace. A continuous deviation bound for a
pair of corresponding cubics is a different, narrower guarantee.

## Folder organization

Keep the existing layout and add repair modules only in later milestones:

```text
Glyphs-mcp/
  src/companions/curve-inspector/
    README.md
    bundle/                         # existing native plugin bundle
    curve_core/                     # existing shared visualization geometry
    glyphs_curve_inspector/
      plugin.py                     # existing Reporter
      controller.py                 # direct bounded repair controller
    curve_repair/                   # canonical shared repair module
      geometry.py                   # diagnostics, regularity and bounds
      supertool.py                  # pinned adaptation and grid candidates
      outline.py                    # native drawing correspondence
      joins.py                      # node adjacency and native raindrop expansions
      coverage.py                   # axis-region sampling/preflight
      native.py                     # detached trials, proposals and application
      provenance.py                 # reproducible bundle consistency checks
    docs/repair/                    # these seven planning documents
    qualification/                  # independent native evidence and probes
    skill/glyphs-curve-repair/       # skill source until managed release registration
      SKILL.md
      scripts/                      # thin helpers importing bundled curve_repair
      references/
  src/glyphs-mcp/tests/              # existing test location; future repair checks
  scripts/build_simple_v2.py         # existing build entry point
  scripts/build_curve_inspector.py   # standalone plugin and skill build
```

The existing Reporter, bundle, `curve_core`, tests and main build script are retained.
Share suitable geometry primitives rather than duplicate formulas. Packaging
the engine separately does not require separating its source repository.

Research snapshot: 2026-10-09. Current local integration reference:
Glyphs MCP V2 checkout at `09b2ac7e51dbe90fe270e9ffb86854f2585205dc`, including
its observed working-tree files. Source provenance and licensing are recorded
in [sources and licenses](sources-and-licenses.md).
