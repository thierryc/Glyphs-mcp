# Negative sidebearings and spacing safeguards

Sidebearings are signed OpenType metrics. Negative values are legal and are not inherently errors.

## Legitimate negative bearings

Common cases include:

- `J` and `j`
- `f`
- Some `Q` designs
- Italics
- Swashes
- Combining marks
- Deliberate stylistic overhangs

A name alone is not evidence. Confirm that the outline geometry supports the overhang on the affected side.

## Suspicious results

Review closely when you see:

- Large negatives on upright `V`, `W`, or `Y`
- Large negatives on both sides of an ordinary base glyph
- A cap sampled only through an x-height reference band
- Bearings that consume most of the word space
- A collapsed or nonpositive advance width

The default guarded policy warns at `-0.05em` and blocks ordinary upright base letters or figures at `-0.10em`. The engine converts these thresholds through the font UPM, so proportional values behave consistently at 1000, 2048, or another UPM. These thresholds are safeguards, not typographic laws.

## Exemptions and overrides

`guards.allowGlyphs`, supported italic overhangs, and mark handling create explicit exemptions. Exemptions preserve the calculated negative value and are reported in `negativeBearingAssessment`.

A mutating apply refuses blocked outliers and low-confidence narrow punctuation. Use `overrides.blockedGlyphs` or `overrides.manualReviewGlyphs` only after reviewing the named glyphs. The result retains the original assessment and records the user override. Never treat an override as an ordinary safe application.

Legacy `clamp` values are absolute font-unit constraints. They are not UPM-normalized typographic safeguards and must not hide the raw `proposed` metrics.

## Tabular evidence

True monospacing requires evidence: fixed-pitch metadata, equal default figures within a small normalized tolerance, established width links, or explicit tabular intent. Typewriter appearance, slab serifs, distress, and family names do not establish monospacing.

## Compact audit conclusion

- True monospaced families often have few or no negative ASCII sidebearings.
- Typewriter-styled proportional fonts may contain localized negative overhangs.
- Contemporary sans-serif families commonly use negatives for `J`, `j`, or `f`.
- Upright sans-serif `V`, `W`, and `Y` generally remain near zero or positive.
- Therefore GEEGEE results near `-0.08em` to `-0.14em` on `V`, `W`, and `Y` should be treated as model failures, not accepted merely because negative bearings are legal.

## Proof strings

Use `HHHOHH`, `HOHOHO`, `AVAYAW`, `JHJOJ`, `nnnon`, `nonono`, `f` beside rounds/verticals/spaces, repeated figures, and narrow punctuation beside capitals, lowercase, figures, and spaces.
