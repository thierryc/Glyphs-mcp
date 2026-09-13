### Variable Font Options

Additional adjustments can be made to variable fonts that affect their axes, fallback mode on legacy systems, and file size.

#### Variable Font Origin

Variable fonts require an _origin master_.
The outlines of this master will be stored in the variable font file.
All other masters are only stored as deltas from the origin master.

By default, Glyphs uses the first master in “File” → “Font Info…” → “Masters” as the origin master.
Designate a different master as the origin by adding the Variable Font Origin custom parameter in “File” → “Font Info…” → “Font”.

A minimal variable font setup requires at least an origin master and one master for each variation axis.
This is described in detail in Minimal Multiple Masters Setup.

The origin master is used as a fallback on operating systems and applications that do not support variable fonts.
Therefore, consider picking a regular master as the origin.
Thereby, legacy systems will show a regular font instead of a thin, bold, or italic font.
Since the regular master tents to sit in the center of the designspace, it requires more deltas to describe the other masters.
This increases the font file size compared to picking a corner master like Light or Light Condensed.
For environments where file size is paramount (for example, webfonts), consider picking the origin master from a designspace corner.

#### Axis Location

When exporting a variable font, its design variation axes will use the same coordinates as the axis coordinates set in Glyphs.
However, in some cases, the coordinates inside the Glyphs file might differ from the desired axis coordinates of the variable font.
A common example is the Weight axis, which in Glyphs is often based on steam widths, but the OpenType specification recommends the Weight axis to use a range of 1–1000.
Similar recommendations exist for the Italic, Optical Size, Slant, and Width axis.

Use different axis coordinates by adding an Axis Location custom parameter to all masters in “File” → “Font Info…” → “Masters”.
Click its value to edit it and assign each axis the coordinates that the master represents in variable fonts.
Further configure the axis coordinates of variable fonts using axis mappings.

#### Axis Mappings

Three different axis mappings for the same weight axis.

For variable fonts, the axis coordinates that the user picks can be transformed to different axis coordinates by the font.
Axis mappings perform these transformations.

By default, variable fonts use a linear axis mapping.
_Linear_ in this context means that each axis coordinate is mapped onto itself and is thus unchanged.
For instance, consider a Weight axis ranging from 44 to 130.
If a font user picks a weight of 95 on a slider, then that value is mapped to 95 (it is left unchanged) and used for interpolation:

The linear axis mapping that is used by default.

The slider is equally sensitive for the entire axis range.
This means that changing the slider value by the same amount changes the interpolation value by the same amount everywhere along the axis.

Axis coordinates are mapped to other values by adding control points to the axis mapping that deviate from the linear diagonal:

A non-linear axis mapping with two control points.

The slider is more sensitive on the lower end than on the higher end.
This means that the same amount of change on the low end of the slider results in larger interpolation value changes than on the high end.

The _internal coordinates_ are the values set in “File” → “Font Info…” → “Masters” → “Axes Coordinates”.
The _external coordinates_ are the result of axis mapping; they are used for interpolation.

Setup axis mapping by adding the Axis Mappings custom parameter in “File” → “Font Info…” → “Font”.
Click its value to edit the mappings:

The axis mappings dialog is split into three panes:

- the axis list;

- a list of the mapping control points of the selected axis;

- a visual editor for the control points of the selected axis.

The mappings list is divided into two columns: the internal coordinates on the left and the external coordinates on the right.
Note that the external coordinates also have the Axis Location custom parameter applied, if set, which is why the internal and external coordinates might differ even for a linear mapping.

Click the plus  button to add a new control point.
The new point will show up in the mappings list and the visual editor.
Alternatively, click on the blue line in the visual editor to add a new control point.

Click a value in the list to edit it or drag a control point up and down in the visual editor.
Move the currently selected point with the arrow keys up/down and left/right.
Hold down Shift for increments of 10 and Command for 100.
The currently selected control point is highlighted in the list and enlarged in the visual editor.
Delete the selected control point by clicking the minus  button.

Add an Axis Mappings custom parameter to a variable font setting in “File” → “Font Info…” → “Exports” to customize the mapping for different variable font exports.

#### Style Attributes Table

The Style Attributes (`STAT`) table is information stored in a font file that gives names to different locations on the variation axes.
This allows software using a variable font to display a style name for every possible axis configuration.

For example, consider a variable font named “Example” that has a Weight axis (200-700) and a Width axis (50–150).
The `STAT` table allows to define names for certain axis locations:

| Weight | Name |
|---|
| 200  |  Thin  |
| 300  |  Light  |
| 400  |  Regular  |
| 500  |  Medium  |
| 600  |  Semibold  |
| 700  |  Bold |

 

| Width | Name |
|---|
| 50  |  Compressed  |
| 75  |  Condensed  |
| 100  |  Normal  |
| 125  |  Wide  |
| 150  |  Expanded |

With this information, applications can construct a style name for arbitrary axis configurations.
Setting Weight = 600, Width = 75 might yield “Example Semibold Condensed”.
Names can be marked as _elidable_.
An elidable name is removed when combined with other names.
For example, the default “Normal” width name may be marked as elidable so that the “Bold Normal” style is simplified to “Bold”.

Glyphs automatically compiles all information required for the `STAT` table from the font instance names and their axis coordinates.
If the `STAT` table is not as desired, customize it by adding the following two custom parameters in “File” → “Font Info…” → “Exports”.

- Add the Style Name as STAT entry custom parameter to instances that differ from the variable font origin on a single axis. Set the value to the four-letter tag of that axis. If, for example, the Regular master is the origin and the Light instance differs from it only on the Weight axis, add this parameter and set it to `wght`.

- Add the Elidable STAT Axis Value Name custom parameter to instances that have an elidable name component on an axis. Set the value to the four-letter tag of the axis on which the instance name is elidable. For example, a Regular instance might need multiple parameters, one for each font axis, since its name is elidable in every case.