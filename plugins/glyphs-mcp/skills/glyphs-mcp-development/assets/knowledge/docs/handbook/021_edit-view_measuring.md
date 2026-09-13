### Measuring

Glyphs offers several ways to determine coordinates and to measure distances between points and curves.

#### Measuring with the Info box

Toggle the display of the Info box with “View” → “Show Info” (Cmd-Shift-I).
The Info box always displays data relevant to the current selection.
If there is exactly one node selected, its coordinates will be displayed.

Select a handle (aka off-curve point, or Bézier control point), and the Info box will also show its delta values (_{∆X} and _{∆Y} difference to the on-curve point) and the total length of the handle (distance to the on-curve point).

Tip:

Quickly and precisely measure a stem or bowl width by selecting two nodes that indicate the width, and see what the Info box displays next to the width symbol.

The _{X} and _{Y} coordinates describe the position of the selection bounding box.
The position is measured from the layer origin at (0, 0) to the part of the selection indicated by the blue point in the Info box.
For example, the transformation box with the center dot selected measures from the origin to the selection center.

See Scaling & Rotating for more on the selection Info box.

Values in the Info box can be edited by clicking the number.
Confirm a new value by pressing Return or by exiting the field.
Use the Tab key to exit the current field and edit the next value in the Info box.
Go back by pressing Shift-Tab.
Pressing Escape exits the current field without entering a different field.
Use the Up and Down arrow keys to increment or decrement the value of a field.
Hold down Shift for increments of 10.

When a component is selected, the Info box of the base letter appears to the right.
The base letter is the original glyph the component points to.
The base letter Info box displays the glyph name, its _{X} and _{Y} offset, its horizontal  and vertical  scale in percent, its slant to the right , and counterclockwise rotation angle .
The arrow  button in the top-right corner will insert the original glyph in the Edit tab string to the left of the current glyph and activate it for editing.

Change the glyph that the component points to by clicking its name in the Info box and choosing another glyph from the glyph list in the subsequent pop-up window.
For more details on working with components, see Reusing Shapes: Components.

Changing the position only has an effect if the component is not automatically aligned.
For more details on automatic alignment, see Automatic Alignment.

#### Measurement Tool

Switch to the Measurement tool  (shortcut L) to see all coordinates of all nodes and anchors at once.

The blue numbers are the _{X} and _{Y} coordinates of the on-curve points, the green numbers are the coordinates of off-curve points, and the red numbers are the _{x} and _{y} delta values between the on-curve points.

Tip:

The _{X} delta values respect the italic angle set in Font Info.
So, an _{X} delta of zero indicates a line exactly in the italic angle.

Clicking and dragging draws a ruler that displays precise measures between all of its intersections with the outlines.
Add Shift to drag a horizontal or vertical ruler.
At the end of the ruler, its angle is displayed in counterclockwise degrees, where zero degrees corresponds to dragging the ruler perfectly vertically towards the top.

The Measurement tool works on all visible glyphs in Edit View.
This also applies to the measurement line:

Temporarily activate the ruler and the display of point coordinates by simultaneously holding down Cmd-Opt-Ctrl.
Press the G key while dragging a ruler to add a guide in measurement mode.
Holding down Command temporarily switches to the Select tool.

#### Measurement Guides

Local and global guides can be turned into a measurement guide.
Click on the guide to select it and click the measurement symbol  in the Info box.

Like the Measurement tool, guides in measurement mode will display the distance between their intersections with outlines or components.
Contrary to the tool, they always do so as long as guides are shown, regardless of which tool is active.

Note that the overlapping paths (such as the curl in the sigma pictured above) are ignored by the Measurement tool or measurement guides.
Such overlapping paths are drawn with a light gray color and removed when exporting a font with the Remove Overlap filter enabled.

#### Measurement Line

When in text mode, enter measurement mode by choosing “View” → “Show Measurement Line”.
The measurement line will display the sidebearings at a given height, ignoring the shape of the glyph at other positions.
More precisely, the numbers displayed indicate the distance between the left or right sidebearing and the point where the measurement line first crosses the glyph outline.
Alter the height of the measurement line by Cmd-Opt-Ctrl-clicking or Cmd-Opt-Ctrl-dragging.
Or switch to the Measurement tool (L) and drag it to the desired height.

In measurement mode, thin gray lines indicate the widths of the glyphs.
Kernings are color coded:
Negative kerning is displayed as light blue, positive kerning as yellow.
The colors can be changed in the settings.