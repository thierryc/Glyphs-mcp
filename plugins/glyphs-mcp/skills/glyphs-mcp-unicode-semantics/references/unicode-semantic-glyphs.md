# Unicode semantic-glyph review for modern fonts

Use this reference when a source contains controls, whitespace, joiners, variation selectors,
suspicious blank glyphs, or zero-advance glyphs. It is for ordinary modern text fonts, not a
universal character-set recipe for legacy encodings, terminal fonts, Last Resort fonts, or
fonts deliberately designed to reveal hidden characters.

## Evidence boundary

Character names and general categories are insufficient. Determine behavior from the current
Unicode Character Database properties, the font's mapping and metrics, normal shaping output,
and, when line breaking is involved, the target layout engine. Unicode explicitly excludes
some visible format controls from `Default_Ignorable_Code_Point`; never turn “all Cf characters
must be blank” into a rule.

For every finding record:

- code point, Unicode name and properties, source glyph name, and export state;
- contours, components, and advance in every master or relevant special layer;
- expected normal rendering and semantic effect on adjacent characters;
- shaping or target-engine evidence actually collected;
- severity, scope, and the smallest safe remedy.

## Classify before changing

| Class | Ordinary glyph behavior | Review focus |
| --- | --- | --- |
| Default ignorable | No visible fallback or advance when unsupported; it may still affect layout | Mapping, geometry, advance, and semantic sequence tests |
| Spacing whitespace | Blank with intentional advance, except higher-level controls | Width relationships, interpolation, and line behavior |
| Combining mark | Usually visible and usually zero advance | Contours, anchors, attachment, and defective sequences |
| Other control or unsupported character | Not automatically ignorable | Deliberate support or visible glyph-0 fallback |
| Visible punctuation or symbol | Visible and normally advancing | Mapping, design relationship, spacing, and breaks |
| `.notdef` | Visible missing-glyph signal at glyph ID 0 | Glyph order, outline, width, and fallback behavior |

Use the UCD version in scope instead of freezing a guessed property list in tooling.

## U+00AD SOFT HYPHEN

U+00AD is an invisible format character that marks a preferred intraword break. It is not a
drawn hyphen. On an unbroken line it must contribute neither a visible shape nor advance. If a
break is taken, higher-level language and layout logic chooses the result; it may insert a
hyphen, change spelling, use a different mark, or show no mark.

For an ordinary modern text font:

1. Treat a U+00AD mapping to a glyph with contours, components, or nonzero advance as a
   release blocker.
2. Prefer omitting an explicit `softhyphen` glyph unless a documented legacy or target-engine
   requirement justifies it.
3. If compatibility requires a mapping, test that exact application. Normal rendering must
   still be invisible and non-advancing; a component copy of `hyphen` is not a safe source.
4. Shape `ther<SHY>apist` and `therapist` normally; visible output and total advance must match.
   Preserving default ignorables can diagnose the mapping but is not normal rendering.
5. Test a forced break at SHY separately in a real line-layout engine. Shaping alone does not
   choose line breaks or language-specific hyphenation.

HarfBuzz normally hides default ignorables by substituting an invisible zero-advance result;
that renderer behavior is not permission to ship a visibly drawn U+00AD glyph.

Do not generalize from the words “soft hyphen”:

- U+2010 HYPHEN is visible punctuation.
- U+2011 NON-BREAKING HYPHEN is visible punctuation with no-break semantics.
- U+1806 MONGOLIAN TODO SOFT HYPHEN is explicitly visible.
- U+2027 HYPHENATION POINT is a visible dictionary or editorial mark.

## Default ignorables and format behavior

Enumerate `Default_Ignorable_Code_Point` from the UCD version in scope. Important families
include CGJ, bidi controls, ZWSP, ZWNJ, ZWJ, WORD JOINER, invisible mathematical operators,
variation selectors, and U+FEFF.

- A default ignorable must not acquire a visible glyph or advance in ordinary text merely
  because the font maps it.
- Invisible does not mean semantically inert. Joiners can alter joining or ligation;
  selectors can choose another glyph; ZWSP and WORD JOINER change break opportunities; CGJ
  affects canonical ordering.
- A font may omit mappings handled by the layout stack. When a target requires explicit
  glyphs, they are normally contourless and non-advancing.
- U+FEFF is primarily the byte-order mark. New content should use U+2060 for word joining,
  while rendering preserves U+FEFF's compatibility semantics when it occurs as text.
- Variation selectors are never visible themselves. Verify base mapping and cmap format 14
  rather than encoding a visible selector glyph.
- A show-hidden font is an explicit product exception, not a modern text-font pass.

## Whitespace is not default ignorable

Do not collapse a blank glyph to zero width merely because it has no contours.

- U+0020 SPACE needs a design-appropriate word-space advance.
- U+00A0 NO-BREAK SPACE is blank and normally matches U+0020's advance.
- U+2007 FIGURE SPACE normally matches the relevant figure width.
- U+2008 PUNCTUATION SPACE should coordinate with punctuation metrics.
- Thin, hair, narrow no-break, and other typographic spaces need deliberate nonzero widths
  appropriate to the design, script, and language.
- Tabs, line feeds, carriage returns, and line/paragraph separators are higher-level controls;
  do not manufacture ordinary visible glyphs for them.

## Marks, controls, normalization, and fallback

- Combining marks are often visible with zero advance. Review anchors and attachment; do not
  strip their contours because a width audit found them.
- U+034F CGJ is an invisible combining-mark exception.
- Check canonically equivalent sequences relevant to the supported repertoire. Precomposed
  and decomposed text should shape consistently where the font claims support.
- C0/C1 controls, unsupported characters, PUA characters, and surrogates are not default
  ignorables and must not silently disappear under that rule.
- Glyph ID 0 must be `.notdef` and should provide a recognizable missing-glyph signal.
- PUA mappings need a documented contract. Flag accidental, duplicate, unstable, or
  unreachable assignments; route icon allocation decisions to the icon-font skill.
- Do not map noncharacters, surrogates, or unassigned code points as public text characters
  without a documented protocol.

## Proof matrix

| Evidence | Minimum proof |
| --- | --- |
| Glyph source | Mapping, export flag, geometry, and advance in every relevant layer |
| Normal shaping | Ignorables disappear without advance while joiner/selector effects remain |
| Whitespace | Blank outlines, intended widths, interpolation, and applicable no-break behavior |
| Combining marks | Base-plus-mark, stacked marks, mark-to-mark, and isolated behavior |
| Normalization | Relevant precomposed and decomposed sequences behave consistently |
| Fallback | Unsupported non-ignorable text shows `.notdef`; unsupported ignorables do not |
| Line layout | SHY, ZWSP, WORD JOINER, NBSP, and non-breaking hyphen in the target engine |
| Compiled font | cmap, glyph 0, metrics, outlines, variation sequences, sanitizer, and checks |

## Trustworthy sources

- [Unicode Standard Annex #14: Line Breaking Algorithm](https://www.unicode.org/reports/tr14/)
- [Unicode Derived Core Properties](https://www.unicode.org/Public/UCD/latest/ucd/DerivedCoreProperties.txt)
- [Unicode PropList](https://www.unicode.org/Public/UCD/latest/ucd/PropList.txt)
- [Unicode FAQ: unsupported characters](https://www.unicode.org/faq/unsup_char.html)
- [Unicode Standard: normalization](https://www.unicode.org/reports/tr15/)
- [OpenType 1.9.1 cmap specification](https://learn.microsoft.com/en-us/typography/opentype/spec/cmap)
- [Microsoft typography: whitespace design](https://learn.microsoft.com/en-us/typography/develop/character-design-standards/whitespace)
- [HarfBuzz buffer flags and invisible glyphs](https://harfbuzz.github.io/harfbuzz-hb-buffer.html)
- [Glyphs Handbook: glyph properties](https://handbook.glyphsapp.com/glyph/)
