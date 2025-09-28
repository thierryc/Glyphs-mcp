### Cap Components

Cap components attach to two nodes.
This is in contrast to corner components, which attach to a single node.
The two nodes need to be next to each other on the same path.
Use cap components for spurs, terminals, flag serifs, and other shapes that appear at the end of strokes.

#### Creating Cap Glyphs

The name of a cap glyph starts with “_cap.” followed by an arbitrary cap name, for example, “_cap.flag”.
There are two possible anchor setups:

Tip:

Place the anchors on a well-known position, such as the x-height or the baseline.
This allows the stem in the referencing glyph to be independent of the overshoot of the cap.

In the first setup, place an “origin” anchor where the first of the two stem nodes should be relative to the cap.
This is a simple setup for simple needs.

Add the two anchors “node1” and “node2” representing both of the attached stem nodes to control the positioning and scaling of the cap relative to both nodes.
This second setup allows for more flexibility when fitting the cap onto stems of varying widths.

#### Using Cap Components

Attach a cap component to two adjacent nodes of the same path by selecting them and choosing “Add Cap Component” from the context menu.
A glyph picker will open, showing only cap glyphs.
Search for the desired cap and insert it by pressing Return.

In Edit View, a cap component is highlighted with a subtle blue background.
Click on a cap component to select it.
Shift-click to select multiple caps.
A selected cap can be copied with “Edit” → “Copy” (Cmd-C) and pasted onto other segments with “Edit” → “Paste” (Cmd-V).
Press the Delete key to remove the selected cap components.
Control-click or right-click a cap and choose “Decompose Cap” to replace the component by its path.
Select a cap component to view its Info box.
(“View” → “Show Info”, Cmd-Shift-I, also needs to be selected.)

Check the “Fit” checkbox to automatically match the size of the cap to the size of the stroke to which it is attached.
Cap components can be replaced, transformed, and aligned like corner components.