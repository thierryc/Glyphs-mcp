# Advanced contextual kerning

Use this reference only after ordinary spacing, groups, and pair kerning are
stable. Context kerning is an exception layer for a complete sequence; it is
not a more powerful replacement for pair kerning.

## Glyphs 4 storage and boundary model

Glyphs 4 stores contextual kerning as an outer context key whose inner mapping
contains numeric values by master ID:

```json
{
  "L * quoteright A": {"MASTER_ID": -40},
  "L quoteright * A": {"MASTER_ID": 80}
}
```

The `*` marks the boundary receiving the additional adjustment. The public
tool uses a safer typed representation:

```json
{
  "entryKind": "context",
  "masterId": "MASTER_ID",
  "sequence": ["L", "quoteright", "A"],
  "boundaryIndex": 1,
  "value": -40
}
```

`boundaryIndex` is one-based in reading order: `1` is `L|’A`, and `2` is
`L’|A`. The tool serializes the native `*` key; callers never submit raw keys.
Glyph names must be exact existing names, the sequence must contain at least
three glyphs, and the boundary must be inside the sequence.

The outer-key/inner-master orientation matters. Duplicating or deleting a
master must add or remove that master inside every applicable context without
replacing other context keys.

## Additive semantics

Contextual values are applied in addition to normal kerning. Before proposing
a value:

1. Confirm spacing and pair kerning already produce the intended base rhythm.
2. Record the ordinary adjustments already active at the target boundary.
3. Treat the contextual number as only the extra correction needed in the
   complete sequence.
4. Inspect every relevant master. Glyphs stores a value per master and can
   interpolate those values between masters.

Do not use context mode for `VA`, `To`, or another ordinary two-glyph pair.
Do not use horizontal `kern` behavior to solve vertical kerning or shaping
that is required for legibility. OpenType uses `vkrn` for vertical kerning and
other features such as `dist` for required script-specific spacing.

## Worked `L’A` review

Use `quoteright` for the typographic apostrophe glyph unless the font uses a
different exact glyph name. Review these as two independent targets:

| Typed target | Native key | Visual boundary | Purpose |
| --- | --- | --- | --- |
| `boundaryIndex: 1` | `L * quoteright A` | `L|’A` | Tighten `L–’` only in the full sequence. |
| `boundaryIndex: 2` | `L quoteright * A` | `L’|A` | Add space before `A` only in the full sequence. |

The numbers `-40` and `80` in examples are illustrative, not recommendations.
Determine actual values through proofing. Both approved adjustments belong in
one atomic batch so either both appear or neither does.

Positive proof strings must contain the exact complete sequence. Negative
controls should include:

- `L’O` to prove the following glyph matters;
- `l’A` to prove the preceding glyph matters;
- `’A` and another apostrophe–`A` occurrence to prove the left context matters;
- surrounding text such as `XL’AX` to inspect run behavior without assuming
  that an isolated Edit View sample represents shaping in a paragraph.

## Reading, coverage, and applying

- `read_document` with `entity="kerning"` returns directional pair and context
  records. Constrain direction, master, keys, or context identity in the
  selector and follow pagination.
- The skill derives coverage from the complete selected evidence, including
  editable exact-glyph records, raw-only records, and per-master counts.
- `preview_change` accepts explicit `set`, `insert`, and `remove` mechanics for
  ordinary pairs and exact contexts in one fingerprint-guarded transaction.

An existing raw context that uses bracket classes, feature-file marked glyphs,
or other manual syntax is returned with `editable: false`, its exact
`rawContextKey`, and no normalized sequence. Never hide, approximate, or
overwrite such a record. Route changes to the OpenType-features workflow.

`value: null` removes the selected master value and removes the outer context
key only when no master values remain. `value: 0` stores an explicit zero.
Duplicate targets, missing glyphs or masters, two-glyph sequences, invalid
boundaries, and non-finite numbers must be refused before mutation.

## Manual feature-code route

Manual contextual GPOS is appropriate when a rule needs glyph classes,
Tokens/Number Values, broader language-system control, or behavior not
representable by one exact sequence. Glyphs documents patterns such as:

```fea
pos L' -40 quoteright' 80 [A Aacute Agrave];
```

Keep the marked glyphs in one contiguous subrun and do not mix incompatible
lookup types in a single lookup. Preserve `# Automatic Code` placement and the
generated `kern` ordering when extending automatic kerning. Variable code
must use a supported interpolation mechanism; static instance-specific values
must not be mistaken for a variable rule.

Apple's AAT `kerx` format 1 also describes contextual, additive kerning and can
involve longer glyph runs. It is useful background, but it is not the storage
or write contract for this Glyphs 4 tool, which targets Glyphs contextual
kerning and OpenType GPOS `kern` behavior.

## Acceptance proof

Stored-value readback is necessary but not sufficient. After applying:

1. Re-list both target boundaries and compare master IDs and values exactly.
2. Re-list ordinary pair kerning and confirm LTR, RTL, and vertical domains are
   unchanged.
3. Inspect the complete sequence and negative controls in Glyphs Context
   Kerning mode, then return to Kerning & Spacing for the ordinary pair view.
4. Test Text Preview/CoreText and at least one external shaping environment or
   exported-font application with `kern` enabled.
5. Disable `kern`: both ordinary and contextual kerning should disappear.
6. For a variable font, inspect named instances and intermediate slider
   positions; for static exports, inspect every relevant master/instance.
7. Confirm only the complete positive context receives the additional advance
   changes. Record any environment that does not exercise GPOS faithfully.

Never claim that stored values prove optical quality or collision clearance.
Never auto-save the source.

## Primary sources

- [Glyphs: Contextual kerning](https://glyphsapp.com/learn/contextual-kerning)
- [Glyphs File Format v4: `kerningContext`](https://github.com/schriftgestalt/GlyphsSDK/blob/Glyphs3/GlyphsFileFormat/GlyphsFileFormatv4.md)
- [Microsoft OpenType GPOS specification](https://learn.microsoft.com/en-us/typography/opentype/spec/gpos)
- [Microsoft registered `kern` feature](https://learn.microsoft.com/en-us/typography/opentype/spec/features_ko)
- [Adobe OpenType feature-file syntax](https://adobe-type-tools.github.io/afdko/OpenTypeFeatureFileSpecification.html)
- [Apple TrueType `kerx` table](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6kerx.html)
- [Google Fonts testing guidance](https://googlefonts.github.io/gf-guide/testing.html)
