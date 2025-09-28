### Opening Font Files

Prefer working with sources (“.glyphs”, “.glyphspackage”, “.ufo”) as described in Source Formats.

Glyphs can open compiled font files of the following formats:

- OpenType, PostScript/CFF flavor (“.otf”)

- OpenType, TrueType flavor (“.ttf”)

- OpenType Collection, TrueType flavor (“.ttc”)

- Adobe Type 1, PostScript Font Binary (“.pfb”)

Glyphs cannot reverse-engineer all the information inside a compiled font file.
Opening such a file and exporting it again will produce a font file different from the original.
For example, some hinting information and OpenType tables are lost when importing a compiled font.
Compiled fonts are opened in a view-only mode.
Choose “File” → “Save As…” (Cmd-Shift-S) to save it to one of the source formats.

The order of the glyphs is written into a glyphOrder custom parameter in “File” → “Font Info…” → “Font”.
Plug-ins can add support for opening additional font formats; see Plug-ins.

#### Font File Importing Behaviors

When opening a font file, Glyphs will try to apply its built-in naming scheme and sync the metrics of composite glyphs with their base glyphs.
These behaviors can be disabled in the settings; see User Settings for “Keep Glyph Names from Imported Files” and “Disable Automatic Alignment for Imported Files”.

#### Opening TrueType Font

TrueType flavor OpenType fonts are imported, maintaining their quadratic Bézier curves.
Glyphs can edit, but not create quadratic curves.
Convert them to PostScript/CFF flavor cubic curves with “Path” → “Other” → “Convert to Cubic”.
This command applies to all selected paths, layers, or glyphs.
Components contained in TrueType fonts are kept.

#### Importing Multiple Fonts Files into a Glyphs File

Import fonts as masters by choosing “File” → “Font Info…” → “Masters” → “” → “Add Other Font”.
See Managing Masters for details.
If the newly added masters are interpolated, ensure they are compatible (see Outline Compatibility).

#### Importing OpenType Features

Some OpenType features cannot be reconstructed when opening a compiled OpenType file.
The features in “File” → “Font Info…” → “Features” show a list of features that should be imported.
Lookups used from multiple features are placed in a prefix named “Prefix”.
Kerning and kerning groups are mostly preserved, but contextual kerning is not.

#### Importing PostScript Hints

Most glyph-level PostScript hints are preserved.
Alignment zones and standard stems are also preserved.
However, most glyph-level hints are not connected to nodes anymore.
In a Multiple Masters setup, drag the blue circle  and triangle  onto outline nodes that fit the hint.
See Stem Hints for details.