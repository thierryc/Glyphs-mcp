# Drawing, languages and acceptance

## Review by shape and use

Use H/O for flat/round alignment and stem relationships, E for horizontals and
counter spacing, N/V for diagonal weight and joins, S for curve transitions and
terminals, R for bowl/leg balance. Review M/W breadth, C/G apertures, Q tails and
U bowls during expansion. Serif length, brackets, taper and contrast often need
local redrawing. High contrast, heavy weights and irregular lettering need
particular care; neither offset nor RMX can decide the intended design.

Judge petite caps beside lowercase at text sizes and small caps both beside
uppercase and in mixed/all-small-cap words. Measure actual stems and counter
space, but assess optical color through reading proofs. Avoid matching every
stroke numerically. Review overshoot separately from flat target height. Existing
source proportions and approved control glyphs guide related shapes; they do not
authorize blind copying of corrections to unrelated letters.

Review spacing before kerning, including mixed full caps/derived caps. Uppercase
kerning groups and values are not authoritative for smaller forms. Check anchors,
mark size and clearance in stacked accents, top/bottom marks and narrow letters.
Use native components where appropriate; avoid decomposing accents just to scale
them uniformly. Font-wide changes to default marks are outside derivation scope.

Correspondence requires contour order, starts, directions, node types and semantic
locations, not equal counts alone. Sample actual intermediate shapes along each
relevant variation direction. Special layers are excluded by default and must be
handled deliberately before production export. Do not clean away designed overlaps
or hint references without review. Newly derived glyph hinting is a later task.

## Language and feature proof

Use Glyphs' current naming conventions: `.sc`/`.smcp` for small capitals and
`.pc`/`.pcap` for petite capitals. Default to `.sc`/`.pc`. Do not map typographic
alternates to phonetic small-cap Unicode characters.

Review automatic `smcp`/`c2sc` and `pcap`/`c2pc` source, including interaction with
`locl`, `ccmp` and ligature features. The lowercase-only features leave full caps
available; all-cap formatting combines both conversion routes. Preserve authored
manual code and language systems. Update automatic blocks only through supported
actions/routes; compile and shape separately when authorized.

- Turkish/Azeri dotted and dotless I need distinct derived mappings under the
  appropriate language systems. Test `i ı İ I` and a word such as `Diyarbakır`.
- Decide sharp-S presentation with the designer and preserve language intent;
  do not infer a universal SS-versus-capital-sharp-S policy from name casing.
- Check encoded `fi`, `fl` and legacy digraphs through their decomposition and
  conversion features rather than introducing unjustified new ligature forms.
- Catalan `l·l`/`L·L` needs a correctly placed middle dot, including feature order
  and the font's existing localized construction.
- For Spanish, inspect `¿Qué? ¡Sí!` in mixed and all-derived text. Pair inverted
  punctuation with its upright equivalent. Derived punctuation ordinarily belongs
  in `c2sc`/`c2pc`, rather than shrinking punctuation alongside lowercase-only text.
- Include AE/OE, accented bases and supported mark combinations from the actual
  font/language brief; do not expand the font's declared language coverage silently.

## Human review record

For each issue record glyph, exact master, region, observation, proof/measurement,
proposed correction, decision and actual follow-up state. Distinguish:

- Pilot accepted: the direction may be expanded.
- Manual adjustment needed: give a precise native editing task, then wait.
- Technically checked: state what geometry/compatibility/feature behavior passed.
- Designer accepted: record the human's actual acceptance and remaining issues.

Fingerprint changes after manual edits are expected evidence. Adopt them only
after fresh inspection and retain them in subsequent reports. Do not treat Keep,
timeout, successful script execution or absence of warnings as optical approval.
For productivity evaluation record actual designer minutes and correction counts
for manual, simple-scale and guided construction; report unmeasured baselines.
