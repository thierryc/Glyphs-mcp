# Accompanying agent skill design

**Skill:** `glyphs-curve-repair`. Its entry, helper and reference now live under
`skill/glyphs-curve-repair/` in the companion and ship in the standalone build.
Global installation and managed-catalog registration have not occurred.

The skill package contains a concise `SKILL.md`, thin helpers importing
the shared bundled engine, references for stars/SuperTool/master verification,
and examples. It must not contain another implementation of curvature,
harmonization or deviation bounds.

## Planned workflow instructions

1. Diagnose the request: static G1/G2, visual balancing, or an interpolation-only
   kink. Route qualified HOI problems to `dekink-native`; disclose its narrower
   domain.
2. Read the advertised environment and bind document, exact glyphs, layers,
   foreground/background and selected joins once. Expand the entire explicit
   scope independently of the Reporter's display cap.
3. Resolve method and tolerance. Default to native stars and 0.001 em maximum
   effective-outline deviation; balancing is off. Explain when extraction or
   general-master verification is unqualified.
4. Obtain immutable source state and coverage. Follow V2's saved-baseline
   requirements for native script work.
5. Analyze and propose using the shared engine and detached native adapter.
   Explain continuity, maximum deviation, join movement, excluded targets and
   sampled verification region.
6. Apply only within existing authorization. Preview-only requests stay
   non-mutating. Recheck exact native guards immediately before application.
7. Verify actual results, including neighboring joins and declared native
   locations. Keep recovery available until the result is resolved.
8. Report success, no-op, refusal, partial application or incomplete coverage
   explicitly, with recoverable state and proposal/job identity when relevant.

The skill must not infer that enabling Curve Inspector authorizes edits, that
an advertised companion capability is callable, or that an unchanged Boolean
smooth flag proves a star proposal is fresh.

## Authorization and recovery language

Respect an existing request to repair. Do not ask again merely because an
unsupported typed edit needs an authorized narrow native script route. A request
to preview authorizes no live edit. A changed method, larger tolerance or wider
scope must be surfaced and resolved before dependent application.

Explain native script restoration precisely: it reloads the saved font and
discards all later unsaved changes. It is not selective rollback. Do not save,
overwrite, install or restart without the user's actual authorization. Existing
job ownership and saved-baseline gates still apply.

## Helper boundaries and packaging

Helpers translate V2 reads and native results into shared engine structures,
construct bounded jobs, summarize proposals and verify engine/package consistency.
They import a bundled module at a pinned revision. They do not load a developer
checkout, download algorithm code at runtime or reproduce formulas in scripts.

A native script can import a qualified installed engine bundle only when its
presence and version are established. If unavailable, the packaging milestone
must provide a supported reproducible delivery route; silently depending on
an absolute path in this repository is not acceptable.

Planned references:

```text
references/native-stars.md          # exact connections, effective outline gate
references/supertool.md             # pinned adaptation, license and refusals
references/master-verification.md   # families, region, lattice and coverage
references/unsupported-cases.md     # degeneracy, topology, HOI qualification
references/recovery.md              # V2 scripts, guards and whole-font reload
```

The concise skill entry links these references instead of embedding a large
mathematical tutorial or host-specific qualification log.

## Example interactions

| User request | Required behavior |
| --- | --- |
| “Preview repairs for these joins.” | Resolve selection; detached star trials; report proposal and coverage; leave source unchanged |
| “Repair these selected joins within 0.001 em.” | Existing repair authorization covers scoped application after exact guards and sufficient verification; report actual result |
| “Keep the nodes fixed and repair handles with SuperTool.” | Clarify through the method description that stored on-curve coordinates stay fixed while handles change; use the explicit handle route; no star fallback |
| “Balance these handles too.” | Enable explicit Tunni option; compare full result to original and recheck G1/G2 and neighbors |
| “Check the whole multi-axis family.” | Resolve all relevant families and locations; preflight 4096-location cap; do not silently reduce the region |
| Native extraction is unavailable | Return a qualified unsupported/refused result; do not describe raw source curves as effective star output |
| Coverage exceeds the cap | Explain requested coverage and propose a concrete narrower region; wait for that scope decision before dependent work |
| Proposal became stale after an HOI edit | Refuse stale application; recompute a new proposal within existing scope |

## Skill acceptance

Milestone 3 must validate discoverable metadata, concise instructions, packaging
and imports; then execute examples against disposable fonts with the native
qualification record. Skill tests must exercise intent, preview authorization,
exact scope and coverage/refusal reporting. Merely generating a `SKILL.md` or
having an MCP connection does not qualify the repair workflow.
