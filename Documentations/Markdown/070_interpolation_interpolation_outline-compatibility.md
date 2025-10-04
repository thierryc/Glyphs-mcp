### Outline Compatibility

Glyph outlines need to be compatible for interpolation to work.
Two glyph outlines are compatible when the following attributes are the same across all outlines:

- the number of paths and the order of their nodes;

- the number of anchors and their names;

- the number of components and their referenced glyphs;

- the order of paths and components (“Filter” → “Shape Order”).

#### Identifying Incompatible Outlines

If the outlines of a glyph are not compatible, a red bar is shown above its ascender line in Edit View and a red corner  in Font View.
Filter for all incompatible glyphs using Smart Filters (Glyphs includes an Incompatible masters Smart Filter by default).

When using masters that are not compatible by design, such as color fonts, disable the red incompatibility indicators by adding the Enforce Compatibility Check custom parameter in “File” → “Font Info…” → “Font” and unchecking it.

Exporting interpolated instances or variable fonts is not possible if there are glyphs with incompatible outlines.

#### Correcting Path Direction

Use “Path” → “Correct Path Direction” (Cmd-Shift-R) as a first measure to fix outline incompatibilities.
This command does three things:

- it analyses the path structure and, if necessary, changes the path direction for each path;

- it normalizes the start node for each path, usually by choosing the node leftmost node at the bottom of the glyph layer;

- it reorders the shapes (paths and components), usually from bottom-left to top-right.

Hold down the Option key to apply the command on all master layers of the selected glyphs (“Path” → “Correct Path Direction for all Masters”, Cmd-Opt-Shift-R).
See Controlling Path Direction for more details.

#### Reordering Shapes

Choose “Filter” → “Shape Order” to show a window with the paths and components from all layers of the current glyph.
Rearrange the shapes such that they are in the same order on all layers.
See Shape Order for details.

#### Master Compatibility

“View” → “Show Master Compatibility” (Cmd-Opt-Ctrl-N) shows the paths, components, and anchors across all masters.

Compatibility view for three incompatible masters: Light, Regular, and Bold.

In this case, a node is missing on the right of the counter of the p (shown in violet).
This leaves a path segment with a larger curvature angle (highlighted in yellow) than on the other masters.
Subsequent segments on the path are marked as incompatible (red).

The following aspects are highlighted in this mode:

- Paths and components are colored based on their shape order. Components are additionally displayed with a checkered pattern.

- For the current layer, a shape order index number is written next to the starting node of each path and in the middle of each component.

- Diagonal lines connect starting nodes, shape centers, and anchors across the masters. Select points to show their connecting lines. Anchors are connected by dashed lines.

- Path segments are colored either green, yellow, or red.Green segments are compatible.Yellow segments are compatible, but their angle differs by more than 20° between masters, indicating that a node might be missing.Red segments are incompatible; there is either a missing segment in other masters, or the segment types do not match (curved segment vs. straight segment).

Fix path direction and shape order related issues as described in Correcting Path Direction and Reordering Shapes.
The points on the connecting lines outside the current layer can be dragged to points of other connecting lines to swap to fix mismatched shapes.
For path segment issues, pinpoint the incompatibility caused by selecting nodes and observing whether they fall on the expected spot in the other masters.

If a path, component, or anchor does not exist on a master, its connecting line will point to the origin at (0, 0) on that master.
Glyphs will label components and anchors with red text in cases where these elements do not match:

The master layers of a glyph might be compatible but still produce undesirable interpolations.

This can be the case when all shapes are in the same order but placed in different locations across the masters.
The Master Compatibility view shows such shape-shifting glyphs with crossing diagonal lines.
Interpolations between these masters might produce the following instances:

Fix shapeshifters by reordering the shapes, either with “Path” → “Correct Path Direction”, “Filter” → “Shape Order”, or by dragging a point of a connecting line to the correct shape.