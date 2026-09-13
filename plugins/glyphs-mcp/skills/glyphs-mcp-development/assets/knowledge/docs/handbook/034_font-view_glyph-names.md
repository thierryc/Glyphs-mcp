### Names & Unicode

#### Glyph Info Database

Glyphs contains a glyph info database.
For each glyph, the database defines:

- the nice glyph name that is used within Glyphs;

- the production name that is used on export;

- the associated Unicode value, when there is one;

- the components, in the case of composite glyphs;

- a default set of anchors;

- the associated marks displayed in the mark cloud;

- the script of the glyph;

- the category and subcategory of the glyph.

Glyphs uses two kinds of names: nice names and production names.
Nice names are used within Glyphs and are intended to be readable for humans.
Production names are used in exported font files and are intended to be read by computers.
See Glyph Name and Production Name for details on both.

Glyphs uses its glyph info database to convert between nice names, production names, and Unicode values.
This glyph info database can be viewed by choosing “Window” → “Glyph Info”.
All glyphs stored in the database are displayed in a searchable table.
Click a column header to sort the table by that column.

Use the methods described in Glyph Properties to override the glyph properties of individual glyphs for a single Glyphs file.
Adjust glyph properties for all Glyphs files by
creating a custom `GlyphData.xml` file.

Suffixed glyphs inherit the glyphs info properties of their unsuffixed counterpart.
For example, A.alt, A.ss01, and A.001 all use the same glyph properties as the unsuffixed glyph A.
However, names like Aalt, Ass01, or A001 would not inherit any properties since they are missing the dot between the base name and the suffix.
While such glyph names are valid, they require all properties to be set up manually.
If possible, it is best to use glyph names from the glyph info database and use dot suffixes for glyph variants.
See Automatic Feature Generation for details on how specific dot suffixes can help generate OpenType features, automatically.

#### Naming Glyphs

Glyph names appear underneath their glyph cell in Grid View or their column in List View.
Edit a glyph name by clicking it once.
When adding a glyph by character (“ä”) or by Unicode name (“uni00E4”), Glyphs will automatically assign a nice name to the glyph (adieresis in this case).

Based on the glyph name, Glyphs can automatically assign Unicode values, a glyph category, subcategory, and generate OpenType features.
See Adding New Glyphs for more details.

This automated glyph renaming can be disabled for a font in “File” → “Font Info…” → “Other” → “Use Custom Naming”.
Note that automatic feature code generation or automated assignment of categories does not work with custom names.
Using a custom glyph info database can provide automated behavior like assigning Unicode values or categories based on glyph names.

Unicode-value-based glyph names start with “uni” followed by four hexadecimal digits or “u” followed by five or six digits.
See Unicode for details.

#### Glyph Naming Rules

A font containing glyphs with invalid names cannot be exported.
Ensure that every glyph name

- only contains letters A–Z and a–z, numerals 0–9, underscore (“_”), hyphen (“-”) or period (“.”);

- starts with a letter (except for non-exporting glyphs and the special .notdef glyph).

In particular, glyph names may not contain white space characters (space, tab, line break) or non-ASCII characters.

In this export results dialog, an error for the Glyph named “₹” is shown.
The glyph should instead use the name “rupeeIndian”.

Not adhering to these guidelines yields an error message at export time stating “Illegal glyph name”, followed by an explanation of where the invalid character is located in the glyph name.
Click the “Show” button to open the invalid glyph in a new tab.
Such error messages can also occur when trying to compile the OpenType feature code in “File” → “Font Info…” → “Features”.

A glyph whose name starts with an underscore is not exported by default.
These names are used by component glyphs such as _part.something, _smart.something, _cap.something, or _corner.something.
See Reusing Shapes: Components for details on component glyphs and their naming rules.

Hyphens are used to indicate the script a glyph belongs to.
Most Latin and Greek glyphs have no hyphen suffix.
This way, the glyph named A represents the Latin A, A-cy represents the Cyrillic A, and Alpha represents the Greek A.
Arabic uses the suffix “-ar”, Hebrew uses “-hb”, Korean uses “-ko”, and Thai uses “-thai”.
Open the Glyph Info window for all available script suffixes.
Special glyphs used in mathematics (“-math”), Braille (“-braille”), Fraktur (“-fraktur”), or music (“-musical”) also use this naming scheme.
Some glyphs, like the Han glyphs used in Chinese, do not have a nice name and use the Unicode name instead.

Alternate glyphs such as small caps and initial/

medial/

final forms use a dot suffix:
The name is the same as the regular glyph but followed by a period (“.”) and an identifier.
For example, the small caps alternate of the glyph x is named x.sc and the initial form of noon-ar is noon-ar.init.
Some suffixes are recognized by Glyphs and used to generate OpenType features automatically.
See Automatic Feature Generation for a list of all special glyph name suffixes.

Dot-suffixes can be chained.
For the automatic feature generation to work, suffixes should be ordered in the same order as the features in “File” → “Font Info…” → “Features”.
For example, x.sc.ss01 is the name of the glyph x as a small cap with the first stylistic set enabled, since stylistic sets are typically ordered after small caps.

Ligature glyphs combine the names of their components with an underscore.
For example, f_f_l is the ffl Ligature.
Script and alternate suffixes can also be applied to ligature names.
Suffixes must be added only at the end of the name and not for every component.
For example, the ligature of lam-ar and alif-ar is named lam_alif-ar, and its final form is named lam_alif-ar.fina.

#### Copy Glyph Names

Control-click or right-click a glyph or a selection of multiple glyphs and choose from the “Copy Glyph Names” menu how to write the glyph names to the pasteboard.

The glyph names can be written in a variety of formats to the pasteboard:

Space Separated

The names are formatted on a single line and joined by single space characters.
Example: “one two three ”.

One per Line

Copies the glyph names with each name on its own line and no other separator characters.

Comma Separated

Formats the glyph names on a single line with a comma and a space after each glyph name.
Example: “one, two, three, ”.

Slashed

Prefixes each glyph name with a slash “/” and joins them together on a single line.
Example: “/one/two/three”.
This format can be pasted into Edit View.

Python List

Formats the names as items of a Python list.
Each name is enclosed in double quotes (`"`) and separated by commas and line breaks.
This format is useful when working with the Macro Panel or when writing scripts.
Example:

```python
"one",
"two",
"three",
```

Unicodes

Writes the Unicode values of the glyphs as hexadecimal numbers to the pasteboard, one per line.
Values are padded to at least four digits with leading zeros.
Glyphs without Unicode values are written as “- # someGlyph”.
If a glyph has multiple Unicode values, they are written on the same line and separated by a comma and a space.
Example:

```
005B
005D
- # bracketleft.case
- # bracketright.case
27E8, 3008
27E9, 3009
```

#### Renaming Glyphs

Click a glyph name to edit it.
Changing a glyph name will also change some of its properties, such as the Unicode value or the category.
If only the suffix after the period is changed, no properties will be modified since the base name stays the same.
For example, renaming eacute to plus will change the glyph properties, while renaming eacute.sc to eacute.pc will not.

See Batch-Renaming Glyphs for details on renaming multiple glyphs at once.

#### CID Mapping

CJK fonts use CID mapping, where glyphs are not accessed by glyph name but by a character identifier (CID).
Glyphs can map nice glyph names to CIDs.
A ROS (Registry, Ordering, Supplement) determines which glyph is assigned to which CID.
Exporting glyphs that the ROS does not cover are added to the end of the CID mapping at export.