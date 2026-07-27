---
title: Unicode assignment tools
description: Implementation and safety notes for reviewing and applying Unicode and Private Use Area assignments.
---

# Unicode assignment tools

Glyphs MCP provides two generic tools for managing Unicode assignments:

- `review_unicode_assignments` reads the complete font map, reports problems, and can propose deterministic assignments.
- `apply_unicode_assignments` applies an explicit reviewed batch after preflight, confirmation, and read-back verification.

The tools are not specific to icon fonts. They operate on Unicode scalar values and glyph export state without interpreting outlines, glyph names, scripts, or character meaning.

## Where PUA is useful

Private Use Area assignments can be appropriate when cooperating users need text characters that Unicode does not define, including:

- icon and symbol fonts;
- CJK gaiji and end-user-defined characters;
- historical and scholarly characters;
- minority-language or phonetic characters awaiting standardization;
- constructed and experimental scripts;
- legacy-encoding round trips;
- closed institutional or application character sets.

Unicode does not define the meaning of PUA values. A project using them must maintain its own agreement between fonts, input methods, applications, and documents.

References:

- [Unicode private-use FAQ](https://unicode.org/faq/private_use.html)
- [Unicode Standard: Private-Use Characters](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-23/)
- [Microsoft end-user-defined characters](https://learn.microsoft.com/en-us/windows/win32/intl/eudc)
- [Medieval Unicode Font Initiative](https://mufi.info/)
- [SIL Charis character set](https://software.sil.org/charis/charset/)

## Where PUA is usually wrong

Do not assign PUA merely to expose:

- stylistic alternates;
- swashes or small caps;
- contextual forms;
- ordinary ligatures;
- localized glyph shapes;
- component or intermediate glyphs;
- a second drawing of an already encoded character.

These are normally glyph variants, not private characters. Use OpenType features, character sequences, or unencoded glyphs as appropriate. See [SIL's font-feature guidance](https://software.sil.org/fonts/features/).

## Review workflow

Selection is the safe default:

```json
{
  "font_index": 0,
  "scope": "selected",
  "allocate_unencoded": true,
  "range_start": "E000",
  "range_end": "F8FF",
  "direction": "ascending",
  "reserved_codepoints": ["E100", "E101"]
}
```

Pass `scope: "font"` to target every glyph, or pass `glyph_names` to override the scope. Even when only a few glyphs are targeted, collision detection scans every glyph in the font.

The allocator:

- preserves existing assignments;
- sorts target names for deterministic results;
- skips occupied, reserved, surrogate, and noncharacter values;
- excludes values from an optional previous map;
- keeps values for removed previous-map glyphs reserved;
- restores a previous assignment for an unencoded glyph when it can do so without collision.

The BMP PUA range `E000-F8FF` is only the default. Custom ranges may include standard Unicode or the supplementary PUAs. When a non-PUA range is used, the response warns that character semantics were not evaluated.

The response classifies each valid current and proposed value mechanically as
`standard`, `private_use`, or `noncharacter`. Classification describes the
codepoint range only; it does not validate the character's meaning.

## Previous maps

A previous map is deliberately small and font-oriented:

```json
{
  "uniE042": ["E042"],
  "medievalAbbreviationSign": ["E5D0"],
  "gaijiFamilyNameVariant": ["F120"]
}
```

It is supplied by the caller. Glyphs MCP does not create or persist a product manifest.

The reviewer reports retained, added, removed, and changed mappings. Removed values remain reserved, and changed mappings are reported as breaking findings.

## Apply workflow

Use the exact proposal returned by the reviewer:

```json
{
  "font_index": 0,
  "assignments": [
    {
      "glyphName": "medievalAbbreviationSign",
      "expectedUnicodes": [],
      "unicodes": ["E5D0"]
    }
  ],
  "dry_run": true
}
```

After checking the dry run, repeat with `confirm: true` and `dry_run: false`.

Before mutation, the tool verifies:

- every glyph still exists;
- every current value matches `expectedUnicodes`;
- every requested value is a Unicode scalar value;
- the resulting whole-font map has no collisions.

The batch runs on Glyphs' main thread. Every changed glyph is read back. Any write or verification failure triggers restoration of all original assignments. The tool never saves the font.

## Deliberate boundaries

These tools do not:

- decide whether a private character is linguistically justified;
- infer Unicode characters from glyph names or drawings;
- define canonical icon or product identifiers;
- generate CSS, TypeScript, accessibility metadata, or Figma assets;
- inspect an exported font's `cmap`;
- migrate PUA assignments to newly standardized Unicode characters.

Those concerns require separate project policy or release tooling.
