### Exports

The “Exports” tab contains the static instances and variable fonts that are created when exporting with “File” → “Export…” (Cmd-E).
Click the plus  button located in the bottom-left of the “Exports” tab to add a new static or variable instance.
Four options are available:

- “Add Instance” adds a new instance named “Regular”.

- “Add Instance for Each Master” adds instances at the designspace locations of each master. For example, if the font has two masters, Thin with a weight of 100 and Bold with a weight of 700, a Thin and a Bold instance will be added with the same axis values as the respective masters.

- “Instance as Master” adds a new master to the “Masters” tab using the outlines and metrics of the currently selected instance. For example, consider a font with two masters—_Thin_ and _Bold_—and five instances—_Thin_, _Light_, _Regular_, _Semibold_, and _Bold_—where the Light, Regular, and Semibold instances are interpolations between the two masters. Select the Regular instance and choose “Instance as Master” to add a _Regular_ master with the outlines and metrics taken from the instance. Now the Light instance interpolates between the Thin and Regular masters, the Regular instance uses the Regular master without interpolation, and the Semibold instance interpolates between the Regular and Bold masters.

- “Add Variable Font Setting” adds a variable font instance. See Exporting Variable Fonts for more information.

Click the minus  button to delete the selected instances.
Select multiple instances by Command-clicking entries in the sidebar, or Shift-click to select a range of instances.
Reorder instances by dragging them to a new position.
The order of instances is just used for organization within Glyphs and does not affect the exported font files.
For more information on interpolating instances, see Interpolation.

#### Active

The “Active” setting controls whether an instance is exported with “File” → “Export…” (Cmd-E).
Deactivated instances are shown with a gray icon in the sidebar.

#### Style Name

The style name appears in the font menu of an application.
Examples include “Regular”, “Bold”, or “Light Italic Display”.
The style name can include the letters A–Z and a–z, the digits 0–9, spaces, and some punctuation marks such as the hyphen.
Characters outside the ASCII range are not compatible with all software.
Instead, add the styleNames custom parameter for style names with Unicode characters.

Some operating systems, applications, and printers do not work with fonts with long font names.
A conservative limit is 20 characters for the overall name (family and style name).
When the font name is too long, consider adding the postscriptFontName and postscriptFullName custom parameters with abbreviated font names.

See the Naming tutorial for more information on good style names and how to shorten them for maximum software compatibility.

#### Weight & Width

The “Weight Class” and “Width Class” values are used to categorize an instance.
Some applications use the weight and width classes to order fonts in a font menu.
When defining the typography of a website with CSS, the weight class is used to access fonts of different weights.

Click the disclosure  button to select from a range of predefined values.
These values follow the OpenType `OS/2` specification: 100, 200, …, 900 for standard weight classes and 1–9 for width classes.
The weight class can be any value from 1 to 1000 if a font family needs more than the nine standard weight classes.
Click a weight class field to manually enter a value ranging from 1 to 1000 (for example, 350 for a Semi Light style).
Note that some applications only work with fonts that use one of the predefined weight classes and reject fonts with in-between values.

Weight and width _classes_ are not necessarily the same as the weight and width _axis coordinates_ (if a font has such axes).
The weight and width classes are used by applications other than Glyphs to order and categorize fonts.
Axes are used internally in Glyphs for interpolation (though they can also be exposed, see Setting up Masters: Axes Coordinates).
Weight and width axes are not bound to the same value ranges as the weight and width classes.

#### Axes Coordinates

Axes coordinates define the location of an instance in the designspace.
The axes of a font are defined in the “Font” tab (see Axes), and masters define the outlines and metrics at specific locations in the designspace of those axes (see Masters: Axes Coordinates).

An instance with axis coordinates between masters is _interpolated_ and _extrapolated_ when it is outside the designspace.
For example, consider a single weight axis with two masters, Light at 40 and Bold at 120.
An instance with a weight of 80 is interpolated.
Instances with weights of 20 and 150 are both extrapolated.
Extrapolated instances are often challenging to get right.
Consider drawing masters at the axes extremes so that all instances are interpolated.

#### Style Linking

Use style linking to connect a bold, italic, or bold-italic instance to its regular instance.
Style linking is used by applications like word processors to switch to the correct font when the user clicks the “**Bold**” button or presses Cmd-I to italicize the selected text.

“Style Linking” has two checkboxes—one for bold and one for italic—and a text field for the name of the base instance.
For example, in a Bold Italic instance, select both checkboxes and enter the name of the normal instance (“Regular”) into the text field.

Style linking only works between fonts with the same family name.
By default, Glyphs uses the family name from the “Font” tab for all instances in the “Exports” tab.
The family name can be overwritten for individual instances by adding a familyNames in “File” → “Font Info…” → “Exports” → “General”.
Fonts generated from different Glyphs files can use the same family name.
This is common when using separate Glyphs files for the Roman and the Italic, which still belong to the same family.

Some applications do not expose a complete list of all styles in a font.
Instead, they only allow the user to select a family and its regular, bold, italic, and bold-italic styles using “**Bold**” and “_Italic_” buttons.
In these applications, fonts that are not linked typically appear as separate entries in a font family picker.
Consider using the following style linking strategy:

- The Bold, _Italic_, and Bold Italic instances of a font family should always be linked to the Regular instance.

- Other italic styles should always be linked to their non-italic counterpart. For example, Medium Italic is marked as the italic of Medium.

Some font designers also link bolds with other styles.
For example, _Semibold_ is marked as the bold of Light.
This hides the _Semibold_ style from the font family picker, making it only available when pressing the “**Bold**” button while the Light style is selected.
Therefore, users may be unaware that the font family includes a _Semibold_ style.

#### Custom Parameters

Instances can have custom parameters.
Some custom parameters exist in the “Font”, “Masters”, and “Exports” tabs.
A parameter in the “Exports” tab will overwrite values set in the “Masters” and “Font” tabs.
For example, a trial version of an instance might add the word “TRIAL” to the end of the family name.