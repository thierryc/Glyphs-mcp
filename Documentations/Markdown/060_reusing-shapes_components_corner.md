### Corner Components

Corner components are open paths that can be fitted onto the corners of a path.
The main usage of corner components is adding serifs to stems, but they can also be used in other circumstances.

#### Creating Corner Glyphs

The name of a corner glyph starts with “_corner.” followed by an arbitrary corner name, for example, “_corner.serif”.
A corner glyph contains an open path flanking the layer origin.
The layer origin is at coordinates (0, 0).
If an anchor named “origin” is placed on the layer, it is used as the origin point.

The open path of the corner component should follow the same direction as it would if it were part of a stem.
Typically, the start node of the path is placed on the same vertical or horizontal axis as the origin point.
Therefore, either the _{X} or _{Y} coordinate of the start node is the same as the _{X} or _{Y} of the layer origin.

The relative position of the end node defines the direction in which the corner expands from the stem.
For instance, place the end node to the right of the layer origin if the corner should expand to the left of the stem.

If the path direction is not set correctly, the corner will extend in the wrong direction (for example, to the bottom instead of to the left).
Fix the direction by selecting the open path and choosing “Reverse Selected Contours” from the context menu.

#### Using Corner Components

Add a corner component to a node in another glyph by selecting the node and choosing “Add Corner Component” from the context menu.
A glyph picker will open, showing corner glyphs.
Search for the desired corner and insert it by pressing Return.

In Edit View, a corner component is highlighted with a subtle blue background.
Click on a corner component to select it.
Shift-click to select multiple corners.
A selected corner can be copied with “Edit” → “Copy” (Cmd-C) and pasted onto other nodes with “Edit” → “Paste” (Cmd-V).
Press the Delete key to remove the selected corner components.
Control-click or right-click a corner and choose “Decompose Corner” to replace the component by its path.

Select a corner component to view its Info box.
“View” → “Show Info” (Cmd-Shift-I) needs to be active.
Click the component name in the Info box to replace it with a different component.
Click the arrow  button to add and activate the corner glyph in Edit View.
Use the  horizontal and  vertical scale fields to change the size of the corner.
This might be useful for increasing the size of serifs for capital letters or reducing it for small caps.
Negative values (such as “-100”) may be used to flip the component.
This allows a left serif to be reused on the right or a bottom serif on the top.
The mirror buttons from the Palette can also be used to flip corner components.

Control the alignment of the corner using the alignment modes in the Info box.
This is relevant for diagonal stems:

- The  left arrow aligns the start node to the diagonal, while the end node of the corner stays put. This mode is typically used for bottom-left and top-right serifs.

- The  right arrow aligns the end node to the diagonal, while the start node of the corner stays put. This mode is typically used for bottom-right and top-left serifs.

- The  left-right arrow is a blend of the left and right alignment. This mode is typically used for ink-traps and similar corners.

- The  x-mark does not align the start or end node to the diagonal.

#### Adjusting the Entry Point of a Corner

The entry point of a corner component is where the stem connects to the corner.
It can be adjusted by adding an anchor to the component glyph.
This is particularly useful for attaching corners to diagonal stems:

Add a “left” anchor to a corner glyph to control where the corner meets the diagonal.
If the open path in the corner glyph is facing to the right, name the anchor “right” instead.

In a typical corner glyph setup with the layer origin at (0, 0) and the start node at _{X} = 0, place the anchor somewhere at _{X} = 0, as shown in the image above.

The anchor must be placed on the line crossing the layer origin and the start node of the open path.

Move the anchor away from the start node towards the baseline to widen corners at the large angle of the diagonal and shorten the corner at the small angle of the diagonal (see the left side of the image above).
Move the anchor in the other direction to achieve the opposite effect (see the right side of the image above).
If no such anchor is placed on the layer, Glyphs assumes it sits at the layer origin (leftmost example in the image above).

#### Adjusting the Exit Point of a Corner

The exit point of a corner component is where the corner connects back to the stem.
It allows the path after a corner to continue at a different position to the path of the stem.
This technique is often used for cupped serifs:

Place a “right” anchor to redefine the end position of the corner.
For a right-facing corner glyph, place a “left” anchor instead.
This anchor is used instead of the end node of the open path as the end position of the corner, which allows the end node to be placed above or below the baseline.

#### Adjusting the Width and Height

As described above, a corner component can be resized using the  horizontal and  vertical fields in the Info box.
By default, the component is scaled by stretching the outlines.
Customize the scaling by adding Intermediate layers to the corner glyph.
These Intermediate layers are then used to scale components by interpolation.

For example, add an Intermediate layer with a “Width” of 150 % and “Height” of 100 % to a corner glyph and make the outline of the corner wider.
Then, change the  horizontal scaling to, for example, 125 %.
The resulting component outlines are interpolated.
Changing the height still stretches the corner, in this example, as no Intermediate layer with a height different from 100 % was defined.

#### Closed Paths in Corners

Corner glyphs may contain closed paths in addition to the one open path.
Closed paths add shapes that can be placed inside or outside the corner.

**Left:** Corner glyph with a closed path.
**Center:** Corner component applied to the bottom-left node of a rectangular path.
**Right:** Preview of the resulting glyph.

The open path must be the first shape on the corner glyph layer.
Reorder shapes with “Filter” → “Shape Order”.

#### Extra Nodes

**Left:** Corner glyph for ink traps.
**Right:** The A glyph with corner components applied to the four extra nodes.

Choose “View” → “Show Nodes” → “Extra Nodes” to show the nodes located on the intersections of overlapping paths.
These extra nodes can also receive corner components.
Attach a corner component to an extra node from the context menu with “Add Corner Component”.

Use corner components on extra nodes for smooth transitions at path intersections, or to add ink traps to stems and crossbars.