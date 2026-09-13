### Batch-Processing

Use batch-processing operations to make changes to one or multiple glyphs at once.

#### Selecting Glyphs

Batch-processing commands operate on all selected glyphs.
Select all glyphs currently shown in Font View by choosing “Edit” → “Select All” (Cmd-A).
Choose “Edit” → “Deselect All” (Cmd-Opt-A) to cancel the selection.
“Edit” → “Invert Selection” (Cmd-Opt-Shift-I) selects only the glyphs that are currently unselected.
Inverting the selection is useful to select all glyphs, except for a few exceptions:
Select the exceptions first and then invert the selection.

#### Batch Commands

The following commands from the “Glyph” and “Path” menus are applied to all selected glyphs.
Commands with an asterisk (*) can be applied to all masters at once by holding down the Option key.

- “Glyph” → “Remove Glyph” (Cmd-Delete)

- “Glyph” → “Duplicate Glyph” (Cmd-D)

- “Glyph” → “Update Glyph Info”

- “Glyph” → “Update Metrics” * (Cmd-Ctrl-M)

- “Glyph” → “Transform Metrics” (see Transform Metrics)

- “Glyph” → “Add Component” * (Cmd-Shift-C)

- “Glyph” → “Create Composite” * (Cmd-Ctrl-C)

- “Glyph” → “Decompose Components” * (Cmd-Shift-D)

- “Glyph” → “Add Image…” (see Font View: Images)

- “Glyph” → “Set Anchors” * (Cmd-U)

- “Glyph” → “Reset Anchors” * (Cmd-Shift-U)

- “Path” → “Reverse Contours” (Cmd-Opt-Ctrl-R)

- “Path” → “Correct Path Direction” * (Cmd-Shift-R)

- “Path” → “Round Coordinates” *

- “Path” → “Tidy up Paths” * (Cmd-Shift-T)

- “Path” → “Add Extremes”, or hold down Option for “Force Extremes” (see Extremes & Inflections)

- “Path” → “Remove Overlap” * (Cmd-Shift-O)

- “Path” → “Transformations” (see Transformations: Transformations)

- “Path” → “Selection to Background” (Cmd-J), or hold down Option for “Add Selection to Background” (Cmd-Opt-J)

- “Path” → “Assign Background…”, or hold down Option for “Clear Background”.

- “Path” → “Swap with Background” (Cmd-Ctrl-J)

- “Path” → “Interpolate with Background” (see Interpolate with Background)

- “Path” → “Other” → “Convert to Cubic”

- “Path” → “Other” → “Convert to Quadratic”

#### Batch-Renaming Glyphs

Rename glyphs by searching and replacing parts of glyph names.
Select the glyphs for which parts of their name should be replaced, choose “Edit” → “Find” → “Find and Replace…” (Cmd-Shift-F), and enter the text to be replaced in the “Find” field.
Then, enter the replacement in the “Replace” field and confirm by clicking “Replace”.
The “Replace” text will replace all occurrences of the “Find” text in any of the selected glyph names.
Leave the “Find” field empty to append the “Replace” text to all selected glyph names.
Select the “Regex” checkbox to enable regular expression matching.
Regular expressions can find and replace patterns of characters.

Examples

Add the suffix “.ss07” to all selected glyphs by leaving the “Find” field empty and writing “.ss07” into the “Replace” field:

Use the regex mode to replace patterns of glyph names.
The dot `.` has a special meaning in regular expressions and is thus preceded by a backslash `\` in the “Find” field.
`\d` matches any digits from `0` to `9`, and the parentheses around the `\d\d` allow the two digits to be references in the “Replace” field by `\1`.

This would replace “someGlyph.cv03” by “someGlyph.ss03” or “otherglyph.cv15.alt” by “otherglyph.ss15.alt”.

See Regular Expressions for details.

#### Filters

Filters can be applied to all selected glyphs from Font View.
See Filters for details on how to apply filters.

#### Palette

Many of the controls in the Palette (Cmd-Opt-P) can be used from Font View.
Both “Fit Curve” and “Transformations” operations can be applied to all selected glyphs.
Palette sections provided by third-party plug-ins may also allow batch editing in Font View.
Controls that do not operate on the entire glyph but only the selected nodes (such as “Fit Curve”) use the selection set in Edit View.
See Palette for details on the individual Palette sections.

#### Plug-ins & Scripts

Some plug-ins and scripts can be applied to all selected glyphs at once.
Refer to their documentation for guidance on batch editing.