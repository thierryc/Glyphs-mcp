### Brushes

Brushes expand path segments using custom outlines.
A brush can be applied to straight and curved path segments and is most useful when applied to open paths.

#### Creating Brush Glyphs

The name of a brush glyph starts with “_brush.” followed by an arbitrary brush name, for example, “_brush.arrow”.
A brush glyph contains a single closed path and two anchors, “start” and “end”.
Choose “Glyph” → “Set Anchors” (Cmd-U) to place anchors on the left and right of the layer.
Typically, the two anchors are placed on the baseline or have both the same distance to the baseline.

A brush glyph may contain only one single closed path.
Use “Path” → “Remove Overlap” (Cmd-Shift-O) to merge multiple closed paths to a single path.
For example, a _brush.arrow glyph might contain the shape of a rightward pointing arrow.
Place the “start” and “end” anchors such that the part of the brush that stretches and curves is in between the two anchors.
Place non-stretching and non-curving parts of the brush before the “start” and after the “end” anchor, like this:

Parts of the brush that should bend when following a curve segment need handles, as shown in the image above.
Add handles to a segment by Option-clicking it.

#### Using Brushes

Select a path segment by clicking it or selecting both of its nodes and choose “Add Brush” from the context menu.
A glyph picker will open, showing brush glyphs only.
Search for the desired brush and insert it by pressing Return.

Typically, brushes are applied to open paths consisting of a single segment.
Brushes can be added to multiple segments by selecting more than one segment before choosing “Add Brush”.
If nodes are selected, choosing “Add Brush” will add brushes such that the selected nodes are the end nodes of the new brushes.

A brush is highlighted with a subtle blue background.
Click on the outline of a brush to select it.
Shift-click to select multiple brushes.
A selected brush can be copied with “Edit” → “Copy” (Cmd-C) and pasted onto other segments with “Edit” → “Paste” (Cmd-V).
Press the Delete key to remove the selected brushes.
Control-click or right-click a brush and choose “Decompose Brush” to replace the component by its path.
Select a brush to view its Info box.
(“View” → “Show Info”, Cmd-Shift-I, also needs to be selected.)

Click the component name in the Info box to replace it with a different component.
Click the arrow  button to add and activate the brush glyph in Edit View.