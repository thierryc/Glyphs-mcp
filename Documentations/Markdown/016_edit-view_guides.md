### Guides

#### Magnetic Guides

When dragging a node selection across the canvas, red lines will appear, indicating when the selection is aligned with other nodes or a vertical metric.
Deactivate magnetic guides temporarily by holding down the Control key.

Likewise, a node or any other object being dragged will snap to all nodes and handles on paths, as well as in components.
When moving close to a node in a component while dragging, Glyphs will fade in small representations of the nodes inside the component.
Disable node snapping by holding down the Control key.

#### Local & Global Guides

Add a local guide to the currently displayed glyph layer by Control-clicking or right-clicking to open the context menu and choosing “Add Guide”.

Pro Tip:

Quickly create a guide using the Measurement tool  by simultaneously holding down Cmd-Opt-Ctrl and pressing the G key after starting to drag a measurement line.

A local horizontal guide  will be added at the click position.
If two nodes are selected while adding the guide, it will be laid through the nodes.
Toggle the display of guides in Edit View by choosing “View” → “Show Guides” (Cmd-Shift-L).

Select a guide by clicking anywhere on it.
A filled knob indicates a selected guide.
Move a selected guide by dragging its knob.
Double-click the knob to turn it perpendicular  to its current orientation.
Quickly duplicate one or more guides by selecting them and holding down the Option key while dragging them to a new position.

Local guides are blue and visible only on the layer on which they have been placed.
Global guides  are red and visible throughout a master.
Create a global guide by holding down the Option key while navigating the context menu and choosing “Add Global Guide”.
Toggle a guide between local and global by selecting it, and from the context menu, choose “Make Global Guide” or “Make Local Guide”.

Lock one or more guides by choosing “Lock Guides” from their context menu.
A locked guide cannot be selected and displays a lock / icon instead of its knob.
Unlock a guide by Control-clicking or right-clicking the knob and choosing “Unlock Guide” from the context menu.

From top to bottom (unselected and selected): local guide, global guide, locked local guide, locked global guide.

Press the Tab key to quickly select the next, or Shift-Tab to select the previous guide.
When a guide is selected, move it using the arrow keys (add Shift or Command for larger increments) or drag its knob with the mouse, just like a regular node.

Change the angle by dragging the guide anywhere outside the knob.
Enter values for its position and its angle in the Info box (Cmd-Shift-I).
Click the lock  icon next to the angle in the Info box to maintain the guide at the set angle until the angle is unlocked  again.

By default, a guide will be positioned relative to the left sidebearing.
Click the right-pointing arrow from a bar in the Info box to position it relative to the right sidebearing or arrow pointing left and right from a bar to position it relative to both sidebearings.
Click the left-pointing arrow from a bar to use the left sidebearing again.
This can be useful for slanted guides, especially when they are global or frequently changing the right side.

Select a guide and click the measurement  icon in the Info box to turn the guide into a measurement guide.
For more details, see Measurement Guides.

Tip:

Use “View” → “Show Metrics Names” to label the vertical metrics.
No guides are needed.

Click “Name” in the Info box of a selected guide to name it.
Guide names are displayed on the left end of a guide:

Global guides are shown on all glyphs by default.
Select a global guide and choose “Edit” → “Info for Selection” (Cmd-Opt-I) to limit the global guide to a subset of glyphs.
The rules for defining the scope of a global guide work the same as Smart Filters.

#### Glyph-Specific Undo History

In Edit and Font View, the Undo mechanism works on a glyph level.
That means that every glyph has its own undo history.

This also implies that certain global actions, especially manipulating global guides, cannot be undone.
That is because global guides are associated with a master and not a glyph, and therefore are ignored by the glyph-level undo history.