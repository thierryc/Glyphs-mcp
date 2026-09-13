### Working with Multiple Fonts

#### Grouping Fonts into Families

A _font_ typically refers to a single font file, like Regular, Bold, or Semibold Italic.
In Glyphs, these font files are exported from the instances added in “File” → “Font Info…” → “Exports”.
In most software applications, fonts are grouped by their family name, which is set in “File” → “Font Info…” → “Font” → “General” → “Family Name”.

Instances and variable font settings can overwrite the family name set in the “Font” tab with a familyNames custom parameter.
Note that the “Default” language is used for grouping; other localized names are only used to display the family name on screen.

Use style linking as described in Style Linking to link the bold and italic styles.
This enables the “**Bold**” and “_Italic_” buttons and the ⌘B and ⌘I keyboard shortcuts common in many applications.

A variable font contains a font family in a single file.
While it is technically possible to put all family members into a single variable font, it may be desirable to split the family across multiple variable fonts.
For example, an italic variable font may be sold separately from the regular variable font.

Add multiple variable font settings in “File” → “Font Info…” → “Exports” to export different variable fonts from a single Glyphs file (for example, a retail version and a trial version with a reduced glyph set).
If the glyph set or OpenType features differ significantly, consider using multiple Glyphs files for the different variable fonts.

#### Glyphs Files, Masters, & Instances

Create a Glyphs file for each instance with “File” → “Generate Instances”.
This command reads the instances of the currently open Glyphs file, converts them to font masters, and creates a new Glyphs file with each of those masters.

Convert a single instance to a master by selecting the instance in “File” → “Font Info…” → “Exports” and choosing “Instance as Master” from the plus  menu.
The master will be added to the “Masters” tab.
Copy a master from an open Glyphs file into the currently open file by choosing “Add Other Master” from the plus  menu in “File” → “Font Info…” → “Masters”.

#### Compare Fonts

Compare two font masters by choosing “Edit” → “Compare Fonts…”
On the top of the “Compare Fonts” window are controls for picking two font files.
Choose from all font files that are currently open in Glyphs.
Below the file controls are pop-up buttons for choosing a master from the font file.
The two selected masters are compared in the center of the window.
Select the same font files twice to compare different masters of the same file.

The window lists the details of the two masters in a two-column layout, comparing font info, master metrics, glyph outlines, and kerning pairs.
These categories can be collapsed or expanded by clicking the disclosure  triangle next to the gray headings.
Click a row to select it.
On the bottom of the window are two buttons: “Use Left” and “Use Right”.
With a row selected, click one of these buttons to write the value from one side to the other.
This can help fix inconsistencies between masters and Glyphs files.

#### Compare Family

Open “Edit” → “Compare Family…” for a comparison of all open documents.
Each document is represented by a column:

Pick from the pop-over menu located in the top-left of the window the attribute to compare.
Choose from the following options: “Component Names”, “Anchors”, “Left Kerning Group” and “Right Kerning Group”, and “Glyphs”.

Empty values are indicated with two dashes (“--”).
If a glyph does not exist in one of the documents, “(missing glyph)” is shown.
The “Glyphs” option shows a red ring with a stroke instead:

Double-click a cell to open the corresponding glyph in Edit View.
Click the filter  button to filter the list of glyphs.
“All” shows all glyphs with relevant information.
“Missing in One” shows glyphs that are not present in all documents.
“Ignore If Missing in One” shows only glyphs that are present in all documents.

Click the pin  button to keep the window above all Glyphs document windows.
The “Update” button reloads all glyph information in case the documents were edited.