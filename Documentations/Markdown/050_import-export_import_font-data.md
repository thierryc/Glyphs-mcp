### Importing Font Data

#### Importing Outlines

“File” → “Import” → “Outlines…” imports PDF, EPS, or SVG files as outlines.
In Font View, multiple files can be selected and imported into the glyphs with a matching name (for example, `A.pdf` into A and `comma.svg` into comma).
If no glyph exists for the file, Glyphs prompts to create a matching glyph or ignore the file.

Click “OK” to skip the file, or “Add Glyph” to add a new glyph matching the filename to the font and import the outlines into it.

In Edit View, “File” → “Import” → “Outlines…” imports a single file into the current glyph.

Vector paths stored in the file are imported as glyph outlines.
Only outlines are kept; the fill color and other styles are discarded.
For PDF files, the stroke thickness is imported as a stroke style.

See Vector Drawing Applications for information on importing outlines with copy and paste.

#### Importing Metrics

Glyphs can import the spacing and kerning of a master from Metrics and AFM files (both of which can be exported from Glyphs, see Exporting Metrics) and from Glyphs and UFO files.

In Font View, choose “File” → “Import” → “Metrics…” to import metrics into the currently open Glyphs file.
Select a file and click “Import”, then an import dialog will appear:

Depending on the selected file, one of the two import dialogs on the right is shown.
**Left:** Metrics or AFM file.
**Right:** Glyphs or UFO file.

Select whether to import kerning values and kerning classes with the respective checkboxes.
When importing metrics from a Glyphs file, kerning values are not supported.
Import kerning values from one Glyphs file into another by copying and pasting them in the Kerning window (“Window → Kerning”, Cmd-Opt-K, see Kerning Window for details).

Importing from a Metrics for AFM file offers controls for glyph metrics in addition to kerning.
Check “Import Metrics” to choose from one of four import modes:

- import left sidebearing and width, adjust the right sidebearing;

- import right sidebearing and width, adjust the left sidebearing;

- import both sidebearings, adjust the width;

- import the width and center the outline (equal sidebearings).

Automatic alignment is disabled for components where the metric values deviate from those derived from automatic alignment, unless “Keep Aligned Components” is checked.
Metrics are imported for all glyphs by default.
Check “Selected Glyphs” to import metrics only for the selected glyphs or all glyphs if none are selected.

#### Importing Feature Files

“File” → “Import” → “Features…” imports OpenType features written in the AFDKO feature language.
Select a file ending in “.fea” and click “Import” to add the contained features to “File” → “Font Info…” → “Features”.
See Features for details on OpenType features.