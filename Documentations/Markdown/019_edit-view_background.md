### Background

Each layer has a background layer, usually simply referred to as “background”.
The background is useful for temporarily storing a path or tracking changes and comparing outlines before and after a manipulation.
Some filters, such as “Filter” → “Hatch Outline”, use the background as a backup layer to work non-destructively.

Tip:

Change the color of background outlines in the settings.
See Appearance.

While working in the foreground, objects on the background are displayed as a subtle red outline with “View” → “Show Background” (Cmd-Shift-B).
If this option is active while in the background, the foreground objects will be displayed in the same way.
Choose “View” → “Show Nodes” → “In Background” to show the on- and off-curve points of the background.
When the background is displayed, snapping will also work with objects on the background layer.

Switch to the background by choosing “Path” → “Edit Background” (Cmd-B).
The window display will darken slightly to indicate that the background layer is active.
This command is a toggle; to switch back to the foreground, use Cmd-B again.

“Path” → “Selection to Background” (Cmd-J) replaces the current content of the background with the active selection; this works in reverse when the background is active.
Simultaneously holding down the Option key changes the command to “Add Selection to Background” (Cmd-Opt-J) and adds the current selection to what is already in the background.
“Path” → “Swap with Background” (Cmd-Ctrl-J) will exchange the foreground with the background.
Empty the background layers of selected glyphs by holding down the Option key and choosing “Path” → “Clear Background”.

Copy the outlines of another font file using “Path” → “Assign Background” into the background layer of all selected glyphs.
Put the same font into its own background to keep track of any other changes.
Selecting all glyphs and choosing “Path” → “Selection to Background” (Cmd-J) has the same effect.