### Segment Components

Segment components apply an open path to straight or curved segments.
The open path can be a single bend segment or a more complex path containing many nodes and curves.

Glyphs will not add additional nodes when bending a segment component to fit a curve segment.
This may reduce the accuracy with which the component follows the curvature of the segment.
However, it ensures that the number of nodes stays the same across masters, allowing interpolation for multiple masters and variable fonts.

#### Creating Segment Glyphs

The name of a segment glyph starts with “_segment.” followed by an arbitrary segment name, for example, “_segment.stem”.
A segment component contains an open path along the baseline and two anchors, “start” and “end”.
Choose “Glyph” → “Set Anchors” (Cmd-U) to place these anchors at the start and end nodes of the open path.
If the “start” and “end” anchors are not placed on the start and end nodes of the path, then the segment component will not match the length of the segment it is applied to.

The start and end nodes of the path should be on the baseline or have both the same distance from the baseline.

#### Using Segment Components

Select a path segment by clicking it or by selecting both of its nodes, then choose “Add Segment Component” from the context menu.
A glyph picker will open, showing only segment glyphs.
Search for the desired segment and insert it by pressing Return.

In Edit View, a segment component is highlighted with a subtle blue background.
Click on a segment component to select it.
Shift-click to select multiple segments.
A selected segment can be copied with “Edit” → “Copy” (Cmd-C) and pasted onto other segments with “Edit” → “Paste” (Cmd-V).
Press the Delete key to remove the selected segment components.
Control-click or right-click a segment and choose “Decompose Segment Component” to replace the component by its path.
Select a segment component to view its Info box.
(“View” → “Show Info”, Cmd-Shift-I, also needs to be selected.)

Click the component name in the Info box to replace it with a different component.
Click the arrow  button to add and activate the segment glyph in Edit View.