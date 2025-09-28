### Drawing Paths

#### Draw Tool

Draw outlines with the Draw tool  (shortcut P as in “Pen” or “Path”).
Click anywhere on the canvas to place a node.
Placing multiple nodes connects them to a path.

Click and drag to create a curved path segment.
Dragging extends two handles from the placed node.
The length of the handles controls the curvature of the segment.
Hold down the Option key to change the handle of the next segment only, and keep the handle of the previous segment as it is.
Hold down the Command key while dragging to change the length of only the next handle while keeping both handles at the same angle.
When dragging, hold down the Space bar to reposition the node.
Click on the first node of a path to close the path.

This handbook uses the term _node_ to refer to on-curve points, _handle_ for off-curve points, and _point_ as an umbrella word for both types.

A node can either be a _smooth node_  or a _corner node_ .
Smooth nodes always keep both of their handles in a straight line.
They appear round and green.
Corner nodes appear square and blue.
Their handles may form a straight line, but they can also form any non-smooth corner.
The size and colors of nodes are configurable in the settings.

_Handles_ (also called _Bézier control points_ or _off-curve points_) control the curvature of their path segment.
They are displayed as small circles and connected to their node with a thin gray line.

In open paths, start and end points are displayed as short perpendicular blue lines.
The start point also features a blue triangle, indicating the path direction.
Points are stored in path direction order, which is significant for some path operations.
See also Controlling Path Direction.

Toggle the display of nodes with “View” → “Show Nodes” → “In Foreground” (Cmd-Shift-N).

#### Pencil Tool

The Pencil tool  (shortcut B) offers a quick way to draw freehand curves, especially when using a drawing tablet.
This includes drawing with Apple Pencil on an iPad using Sidecar.
The resulting paths will need some cleaning up (see Editing Paths) because Pencil paths usually contain too many nodes in an attempt to reproduce the pencil drawing faithfully.

#### Primitives

Glyphs offers rectangles and ellipses as built-in primitive shapes.

Click the Primitives tool /, or press F to activate it.
Click and hold the Primitives tool icon or press Shift-F to switch between the two shape options.
Alternatively, use “Draw Circle” or “Draw Rectangle” from the context menu to switch between the two modes.

Click once on the canvas to create a primitive by entering its measurements with the keyboard.
Click and drag to draw it directly into the edit area.
Hold down Shift for a perfect square or circle.
Hold down Option to draw the shape from its center.