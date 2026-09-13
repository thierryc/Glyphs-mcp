#### Shape Order

“Shape Order” dialog window:

One column per master/

alternate/

intermediate layer.
Drag to reorder shapes within a column.
The insertion position is highlighted in blue.

The “Shape Order” filter lists all shapes (paths and components) of a glyph across all layers.
Paths are shown in navy blue; components in brown.
Each column lists the shapes of a master/

alternate/

intermediate layer.
Click and drag a shape to reorder it within its column.
Confirm the chosen shape order with “OK”, or revert to the original shape order with “Cancel”.

Columns are separated by a gray gutter if there are multiple independent interpolations for the glyph.
That might be the case when using intermediate layers or when employing a complex master setup (for example, when condensed masters interpolate independently of extended masters).

The “Shape Order” filter is useful when “Path” → “Correct Path Directions for all Masters” (Cmd-Opt-Shift-R) does not yield the desired master compatibility.