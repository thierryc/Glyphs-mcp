# LLM judgment — RV01

**This is the executing Codex LLM’s self-assessment, not an independent or blinded judgment.** Numerical assertions are in `assertion-index.json`. The evaluator wrote the scripts and observed their revisions; no human or second-model agreement is claimed.

Scale: 1 blocked/misleading; 2 substantial intervention; 3 workable with friction; 4 minor friction; 5 smooth and verifiable. Correctness scores concern strength of final evidence, not first-attempt success rate.

| Task | Correctness evidence | Design usefulness | Focused skill | Workflow effort | Delivery |
|---|---:|---:|---:|---:|---:|
| T01 — Live layer and selection inspection | 4 | 4 | 4 | 3 | 4 |
| T02 — Fractional width change and restoration | 5 | 4 | 4 | 4 | 4 |
| T03 — Start-node correspondence and interpolation repair | 5 | 5 | 4 | 4 | 4 |
| T04 — Local handle modification | 4 | 2 | 3 | 3 | 4 |
| T05 — Add a stem midpoint | 4 | 2 | 3 | 3 | 4 |
| T06 — Remove a redundant point | 4 | 4 | 3 | 3 | 4 |
| T07 — Native extrema placement | 4 | 4 | 3 | 3 | 4 |
| T08 — Corresponding cubic split across masters | 4 | 3 | 3 | 3 | 4 |
| T09 — Create, run and revise an audit snippet | 4 | 4 | 4 | 4 | 4 |
| T10 — Review existing OpenType behavior | 4 | 4 | 1 | 3 | 4 |
| T11 — Create and verify an OpenType feature | 4 | 2 | 1 | 3 | 4 |
| T12 — Diagnose and correct feature code | 4 | 4 | 1 | 3 | 4 |

## T01 — Live layer and selection inspection

Twelve layer IDs, advances and bounds and three selected nodes agree with the native oracle. Bounded and empty reads are explicit. The agent used the wrong selector key in an extra missing-glyph control; its named-target assertion remains unverified.

Use the documented glyph selector id; avoid guessing field names.

## T02 — Fractional width change and restoration

The three +12.375 advances are exact. Every recorded non-width property and native object is preserved. Undo restores data and clears Edited; Redo replays exactly; discard restores exact data but leaves the native dirty indicator.

No product change justified by this case. Retain native dirty-state parity.

## T03 — Start-node correspondence and interpolation repair

V2 proposes only two permutations. The live result matches the original contour phases and retains objects. Native Light interpolation of the deliberately shifted source has a collapsed outline; the verified original correspondence removes it. The defect was deliberately seeded, not found in upstream Roboto Slab.

The existing supported job is effective. Keep exact reference/master/path scope and a native interpolation proof.

## T04 — Local handle modification

First request +2.5 rounded to +3. The corrected snippet moves precisely one off-curve per master and preserves node metadata, anchors, widths and grid settings. The visual change is under one unit and no aesthetic improvement is established.

Add a tested fractional-coordinate recipe to focused scripting guidance.

## T05 — Add a stem midpoint

The first Black midpoint rounded 102.5 to 103. Corrected insertion gives three exact collinear midpoints and unchanged outlines. Extra points are useful only for a later design operation; adding them is not intrinsically better interpolation.

Teach exact read-back, native grid behavior and a stated reason for adding a node.

## T06 — Remove a redundant point

The original guard rejects the rounded setup rather than removing a non-midpoint. After precise fixture creation, only the three seeded redundant nodes disappear. A perturbed .125-unit negative control is rejected before any partial write. This is a deliberately narrow snippet, not a general curve simplifier.

Retain prevalidation across all masters; never generalize this deletion rule to curved segments.

## T07 — Native extrema placement

Native addNodesAtExtremes adds seven on-curves and fourteen handles per master. The first call exceeds the .05-unit geometry tolerance. Rounding suppression preserves the native result with numerical control-polygon deviation bounds below 1.5e-12 across six contours. Native compatibility and collateral data are retained.

Recommend native extrema with precision protection and reinspection; do not imply that independently added extrema always correspond well on other fonts.

## T08 — Corresponding cubic split across masters

First split changed shape by .395–.451 units despite matching node counts and native compatibility. Corrected split preserves three master curves and native Light/Medium/Bold interpolations within 6e-13. The new on-curve is a homologous editing landmark, not demonstrated improvement to the already-correct design.

Explain the distinction between geometric preservation, compatible indexing and better design; prefer explicit bounded native scripts to a new topology engine.

## T09 — Create, run and revise an audit snippet

The installed scaffolder creates and validates the script. Native revision 1 reports twelve exact rows; actual revised file 2 adds anchor names and remains read-only. Missing glyph/master and over-limit inputs are rejected. Static validation is kept separate from loaded revision evidence.

No additional tool needed. Keep explicit font/master arguments and bounded output.

## T10 — Review existing OpenType behavior

Configured focused skill is blocked by retired tools and an apiMajor gate; it is not part of the current lean package. Separately authorized native review agrees exactly with an independent source parser. Seven behavior checks cover liga on/off, frac, ss01, smcp, lnum and Romanian locl. This is sampled coverage, not an exhaustive feature audit.

Replace the obsolete installed feature instructions through managed setup; route to authorized native coding and focused compile/shaping guidance.

## T11 — Create and verify an OpenType feature

Native ss20 compiles and a real exported TTF substitutes g.ss01 only when enabled. Existing code and glyph data stay intact. The pinned export example fails with FontPath; fontPath works. ss20 intentionally duplicates existing ss01 as an isolated test, so it should not ship as a design improvement.

Add verified Glyphs 4 argument names and require actual output/shaping evidence. Use the existing feature in production.

## T12 — Diagnose and correct feature code

The native compiler returns false and identifies the missing glyph, ss20 and line 1; corrected code returns true. Success is not inferred from a truthy tuple. The source of prior features is preserved. The configured feature skill remains unusable even though the authorized native coding route works.

Document structured native compiler results and show one failure-to-correction loop.

Overall: **3/5** for the mixed experience. The supported MCP workflows are closer to **4/5**. The main friction is the script author’s native-API assumptions and missing/obsolete focused guidance, not evidence that the seven-tool architecture needs expansion. A successful mathematical edit is not automatically a useful design edit.
