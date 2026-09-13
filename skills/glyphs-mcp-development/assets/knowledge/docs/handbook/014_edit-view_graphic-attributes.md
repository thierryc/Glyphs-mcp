### Graphic Attributes

Paths can be styled with graphic attributes.
These attributes include stroke styles, fill styles, and masking.
The attributes are applied to a path in the Palette (“Window” → “Palette”, Cmd-Opt-P) and are accessible when “View” → “Show Info” (Cmd-Shift-I) is active and a path is selected.

Copy the attributes of one path to another with the context menu:
Choose “Copy Attributes” on a path and apply them to another by choosing “Paste Attributes”.

#### Creating Strokes

**Left:** an open path 

**Center:** the path with a stroke 

**Right:** the expanded outline

Expand a path to a shape by selecting one or more of its points and entering a stroke width and height in the “Stroke” section in the Palette.
The stroke width (_{W}) and stroke height (_{H}) are measured in font units.
If no height is set, then the width is used for both dimensions.
Below the width and height fields are controls for the stroke placement ( along the path,  to the left of the path,  to the right of the path) and controls for the stroke ends (flat, square, round, round inset, aligned to an axis).

A stroke can be applied to both closed and open paths.
For closed paths, select the “Fill” checkbox from the Palette to fill the path delineated by the new outlines.

The original path is displayed in a light gray color, while the stroke outline is black.
A stroke path can be converted to a conventional outline by choosing “Expand Outline” from the context menu.
Hold down Option to expand outlines on all masters.

#### Masking

Select a path and check “Mask” from the Palette to subtract the path from all shapes below it.
Applying a mask is a non-destructive action; the path can still be moved and modified.

Subtracting a circle from a square by applying a mask to the circle path.

The subtracted parts of paths are drawn in a light gray color, while the exporting outline is drawn in black.

Masking is based on the order of shapes, since a masking path only affects shapes below it.
Change the shape order by choosing “Filter” → “Shape Order”.
Drag the shapes into the desired order and confirm with “OK”.