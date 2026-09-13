### Transformations

The “Transformations” section transforms points, paths, components, anchors, guides, images, and more.
The following transformations are supported:

- mirror the selection horizontally  or vertically ;

- scale  or reverse scale  the selection;

- rotate the selection clockwise  or counterclockwise ;

- slant the selection left , right , down , or up ;

- align the selection left , right , to the top  or bottom , center it vertically  or horizontally ;

- perform boolean operations ( union,  subtraction,  intersection) on paths.

Transformations can be applied in both Font View and Edit View.
According to the selection, the transformation applies to segments, paths, or complete glyph layers.

The buttons to the left and right of text fields perform opposite transformations.
For example, clicking rotate counterclockwise undoes the transformation caused by clicking rotate clockwise.
These opposing transformations are not subject to rounding errors that might be introduced by the unit grid.
See Grid Spacing & Subdivision for details on the unit grid.

#### Transformation Origin

All transformations (except for alignment) are performed with respect to a transformation origin.
The top row of the “Transformation” palette controls this origin point.

The transformation box  places the transformation origin with respect to the selection bounding box.
Either one of the four corners, or the center of one of the four edges, or the center of the selection box can be defined as the transformation origin.

The reference point  uses the transformation origin as defined by the Scale tool (S) or the Rotate tool (R).
Using one of those tools, click on the canvas to define the transformation origin.
The point is indicated as a red ring  with a crosshair when using the Scale/Rotate tool, and just as a crosshair  when using any other tool.

The metrics point  places the transformation origin at one of the metrics defined in “File” → “Font Info…” → “Masters” → “Metrics”.
Choose either the baseline, half or full x-height, or half or full cap height.
For CJK glyphs, the layer dimensions control  is displayed instead.
It places the transformation origin at the center of the layer (half of the width and centered between the ascender and the descender).

#### Mirroring

The mirror buttons / reflect the selection to the other side of the transformation origin.
Horizontal  mirroring reflects across the horizontal center of the layer when a metrics point defines the transformation origin.

Mirror with the transformation origin positioned in the metrics point control at either half the x-height or half the cap height to preserve overshoots.
For example, mirroring an n that overshoots the x-height will result in an u shape that overshoots the baseline.

Mirroring a corner component (see Corner Components) will turn a left corner into a right corner and vice versa.
Mirroring a glyph component upside-down will reverse the assignment of top and bottom anchors in the original glyph.
This way, a top mark can be used as a bottom mark by mirroring the component.

#### Scaling

Scaling by 120 % using an origin of transformation box center and transformation box bottom-left.

Click the scale  button to scale the selection by the specified percentage.
Percentages larger than 100 % increase the selection size, percentages smaller than 100 % decrease the size, and a percentage of 100 % does not change the size.
The scaling factor along the horizontal axis (top field) and the vertical axis (bottom field) can be defined independently.
The top field is used for both axes if the lock  icon is locked.

Reverse scaling is helpful since a scale of 120 % would not be undone by simply scaling to 80 %, but by scaling to 83.3… % (= 100 %/120 %).

The reverse scale  button undoes a scaling operation.
This is not the same as scaling down:
Scaling with the scale button by a percentage smaller than 100 % (for example, 75 %) shrinks the selection.
Scaling with the reverse-scale button by the same percentage returns the selection to its original size.
Similarly, a selection that was enlarged to a value larger than 100 % with the scale button can be undone using the reverse-scale button.

#### Rotating & Slanting

_Slanting_ is sometimes also referred to as _skewing_.

Rotate the selection with rotate counterclockwise and rotate clockwise.
Slant the selection with slant left, slant right, slant down, and slant up.
Note that slanting a selection twice by a certain amount does _not_ yield
the same result as slanting it once with double the amount.

#### Aligning

The align buttons (left, horizontal center, right, top, vertical center, bottom) can be used on points, complete and partial paths, anchors, and components.
Aligning is always done relative to the bounding box of the selection.

Quickly align the selected points with “Path” → “Align Selection” (Cmd-Shift-A).
This command respects the setting for the transformation origin.
See Editing Paths for more details.

#### Boolean Operations

The bottom row of buttons combines closed paths with boolean operations:  union,  subtraction, and  intersection.

From left to right: two overlapping paths, union, subtraction, and intersection.

Union removes the overlaps in all selected paths (or all paths of the layer if there is no selection).
Subtraction removes the selected paths from the unselected paths.
Paths involved in the subtract operation are merged first to achieve consistent results.
Intersection keeps only the parts where the selected paths overlap the unselected paths.
Both subtraction and intersection use the frontmost path as the selected path if there is no selection.

A union operation can be applied to all glyphs on export using the “Remove Overlap” option.
See Options for details.