#### Transformations

The Transformations filter is split into three dialogs: “Transform Metrics”, “Transformations”, and “Interpolate with Background”.

###### Transform Metrics

“Glyph” → “Transform Metrics” assigns either a new width or new sidebearings to the selected glyph layers.

Enable “Width” to assign a new width to all selected glyphs.
Check “on both sides” to modify both sides equally to match the new width.
Otherwise, the points on the layer keep their original coordinates.

Uncheck “Width” to set new sidebearings.
Control whether the left sidebearing (“LSB”), the right sidebearing (“RSB”), or both should be changed using the checkboxes next to their fields.
If “Relative” is selected, the “LSB” and “RSB” values are added to the current sidebearings (or subtracted if the entered values are negative).
Otherwise, the “LSB” and “RSB” values overwrite the existing sidebearings.

###### Transformations

This type of transformation is also known as an _affine transformation_.

“Path” → “Transformations” applies a linear transformation to the selected points or selected layers.

“Translate” moves points by a given _{X} and _{Y} value.
“Origin” defines the point from which the transformation originates.
“Scale” scales the selection along the  horizontal and  vertical axis.
If the lock button is locked , the horizontal value is used for both axes.
“Slant” skews the selection without optical correction.
Click the “Slant” label and choose “Cursivy” for an optically corrected skew.
Note that “Cursivy” requires horizontal and vertical metrics to be set in “File” → “Font Info…” → “Masters” → “Stems”.

###### Interpolate with Background

“Path” → “Interpolate with Background” results in an interpolation of the foreground and background layers.

A value of 0 % leaves the foreground unchanged; 100 % replaces the foreground with the background, and values in-between result in an interpolated shape.
Use a value below 0 % or above 100 % to extrapolate.
Note that this filter does not work if the foreground and background are not compatible.

###### Custom Parameter

The custom parameter rule is as follows:

```filter
Transformations; LSB:`LSB`, RSB:`RSB`; Width:`Width`; ScaleX:`Scale X`; ScaleY:`Scale Y`; Slant:`Slant`; SlantCorrection:`Cursivy`; OffsetX:`X`; OffsetY:`Y`; Origin:`Origin Metric`
```

`LSB` and `RSB` set the left and right sidebearings.
Prefix these values with a `+` (plus), `-` (minus), `*` (asterisk, multiply), or `/` (forward slash, divide) symbol to change the sidebearings relative to their current values.
`Width` can be prefixed by `+` or `-`.
For example, to multiply the LSB by 2 and add 15 to the RSB, use the following filter rule:

```filter
Transformations; LSB:*2; RSB:+15
```

`Scale X` and `Scale Y` are percentages where a value of 100 does not scale, < 100 scales down, and > 100 scales up.
Set `Cursivy` to _{0} to disable slant correction;
it is _{1} by default.
Set `Origin Metric` to _{0} for cap height, _{1} for ½ cap height, _{2} for x-height, _{3} for ½ x-height (default), or _{4} for baseline.

For example, the following rule sets the width of all glyphs to 700, scales the glyph outlines to 120 % (both horizontally and vertically), cursivies the outlines to a 14° angle (adding `SlantCorrection:0` would use normal slanting), and moves the outlines by 8 units to the right and 22 units down such that all these transformations originate from the x-height:

```filter
Transformations; Width:700; ScaleX:120; ScaleY:120; Slant:14; OffsetX:8; OffsetY:-22; Origin:2
```