# Dactylotype Black Condensed spacing blocker

## 2026-08-31 — exact translations are rounded to the font grid

- Source: `/Users/thierryc/Documents/fonts/Dactylotype/Dactylotype.glyphspackage`
- Live document: `doc_d40087b45954459cbff757ed10a167e3`
- Regular master: `0578215A-7423-43EB-8AD4-4C95A1C78DFA`
- Black Condensed master: `20B80D33-B5FE-4CBE-AB86-1B0C04FA398E`
- Base fingerprint: `sha256:67bec72f18185222cf6d79fb492fbc98b55ab0ec0112862bbea1155a5bdba506`
- Runtime: `2.0.0+ab7bda802f32`
- Immutable preview: `preview_a1d29104d4034bcf982947f6899da4c9`
- Proposed fingerprint: `sha256:a0ed499facb1694af6d31375e703581c411ae9cb974429347cf132ef5b735ea1`
- Result: non-applicable `requested_effect_mismatch`

The read-only audit paired all 423 Regular and Black Condensed master layers.
The requested spacing rule was the nearest integer to 75% of each observed
Regular left and right sidebearing. Empty layers used 75% of the corresponding
Regular advance width. Negative targets remained valid signed spacing.

The plan contained 199 directly editable nonempty layers, 86 empty layers, and
138 layers with active automatic alignment (`isAligned` or
`hasAlignedWidth`). There were no metrics-key conflicts. Automatic alignment
was preserved: actively aligned composites were not translated independently;
only their desired width was requested so native Glyphs inheritance remained
authoritative. The preview contained 613 operations and 484 exact
postconditions.

Detached native verification found 202 unrelated geometry mismatches. Glyphs
rounded translated fractional node x coordinates to the font's 1-unit grid,
although the translation operations requested exact coordinates. Examples
include:

- `ampersand`: `1221.159` requested, `1221` observed;
- `ampersand`: `541.002` requested, `541` observed;
- `ampersand`: `688.626` requested, `689` observed;
- `braceleft`: `239.514` requested, `240` observed;
- `braceleft`: `156.902` requested, `157` observed.

These are not automatic-alignment-owned fields, so semantic verification
correctly retained the existing `requested_effect_mismatch` blocker. The
workflow stopped at this first blocker as requested. No apply or save call was
made.

A read-only final check found the live document clean at the base fingerprint.
The Black Condensed `A` remained at width 1263 with bounds x `31.088` and right
space `24.904` (approximately LSB 31 and RSB 25).

If work is resumed after the fixed runtime is deployed, a new semantic preview
must retain exact fractional translations with no native grid rounding.
That follow-up was not executed in this run.

## Superseded interim workaround

An interim workspace change treated bounded native coordinate rounding as
authoritative. That behavior was never applied to this live font and is no
longer the v2 contract.

V2 now suppresses rounding centrally with the Glyphs 4 layer flag and a
temporary zero-grid fallback. `quantizer="exact"` is the only supported
quantizer. A fractional request that becomes integral or disappears into a
zero-change result is blocked as `requested_effect_mismatch`; grid settings and
global automatic alignment are restored and never used as persistent policy.

Regression coverage passes for semantic equivalence, the mutation kernel,
spacing geometry, application, transactions, the document adapter, staged
Python, contracts, and bundle assembly. A repository-wide run excluding one
unrelated pre-existing README/reference synchronization failure passed 1,690
tests with 3 skips.

This is a workspace implementation result, not a live-font result. The runtime
was not installed or reloaded, the historical preview was not applied, and the
Dactylotype document was not changed or saved during implementation.
