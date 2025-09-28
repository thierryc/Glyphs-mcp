### Setting up Masters

Interpolation requires at least two masters.
Add masters in “File” → “Font Info…” → “Masters”.
Click the plus  button located in the bottom-left of the window to add a new master.
See Managing Masters for details.

Tip:

Give each master a descriptive name such as Light, Regular Condensed, or Bold Caption, and pick a representative master icon.

#### Axes Coordinates

The “Axes Coordinates” of a master indicate its position in the designspace.
Add masters and set their axis coordinates such that the designspace is covered by the masters.
For a single Weight axis, two masters suffice:

| Icon | Master Name | Weight |
|---|
|  |  Light  |  300  |
|  |  Bold  |  700  |

Adding a third master in the middle (for example, Regular at 400) allows for finer control over the interpolation.

The values for the “Axes Coordinates” fields can be chosen freely.
For the Weight axis, the median vertical stem width can be used as axis coordinate values.
For instance, a Light master with a stem width of 45 might use that as its Weight coordinate, while a Bold master uses its stem width of 160.
A more abstract axis, such as Serif, might use a range from 0 to 100, with no serifs at 0 and long serifs at 100.

An Italic axis does not necessarily need to flip to different outlines.
Instead, it may smoothly transition from an upright to an italic angle.
Such an Italic axis may use a larger range like 0–100.

Axes that do not smoothly transition, such as an Italic axis where the glyphs flip to different outlines, use a range from 0 to 1.

Add the Axis Location custom parameter to use a different axis range for variable fonts.
This is particularly relevant to registered axes such as Weight and Optical Size.
See Axis Location for details.

Axis coordinates are spread linearly in the designspace.
For variable fonts, the Axis Mappings custom parameter can be added for non-linear axes ranges.
See Axis Mappings for details.

#### Minimal Multiple Masters Setup

A minimal Multiple Masters setup requires one origin master and one master for each axis.
The “Axes Coordinates” of the origin master differ from each other master on a single axis.
For example, consider a font with a Weight and Width axis.
Then, the following minimal master setup is possible:

| Icon | Master Name | Weight | Width |
|---|
|  |  Light Condensed  |  300  |  50  |
|  |  Light  |  300  |  80  |
|  |  Bold  |  700  |  80  |

The Light master is the origin master.
Its coordinates differ from the Light Condensed only on the Width axis and from the Bold only on the Weight axis.
The Bold, for example, cannot be the origin master since its coordinates differ from the Light Condensed on both the Weight and Width axes.

See Variable Font Origin for information on choosing the origin master.
The choice of an origin master only matters to variable fonts; for static instances, Glyphs automatically determines the origin master.

#### Elaborate Multiple Masters Setups

While a minimal Multiple Master setup already covers the entire designspace, it offers little control over the design of instances that differ from the origin on multiple axes.
For instance, the minimal setup example in the above subsection can produce a Bold Condensed instance, but its outlines might not be satisfactory.

A more elaborate Multiple Masters setup would include masters at all designspace corners:

| Icon | Master Name | Weight | Width |
|---|
|  |  Light Condensed  |  300  |  50  |
|  |  Light  |  300  |  80  |
|  |  Bold Condensed  |  700  |  50  |
|  |  Bold  |  700  |  80  |

Add intermediate masters as needed to fine-tune the design along the interpolation axes.
A complex Multiple Masters setup can span across many masters:

| Icon | Master Name | Weight | Width |
|---|
|  |  Light Condensed  |  300  |  50  |
|  |  Light  |  300  |  80  |
|  |  Light Extended  |  300  |  150  |
|  |  Regular Condensed  |  400  |  50  |
|  |  Regular  |  400  |  80  |
|  |  Regular Extended  |  400  |  150  |
|  |  Bold Condensed  |  700  |  50  |
|  |  Bold  |  700  |  80  |
|  |  Bold Extended  |  700  |  150  |