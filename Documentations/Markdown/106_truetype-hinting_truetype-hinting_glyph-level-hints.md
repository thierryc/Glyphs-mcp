### Glyph-level Hints

Add glyph-level hints with the TrueType Instructor tool  (shortcut I).
Note that the TrueType Instructor tool uses shortcuts without modifier keys, which are usually reserved for tool switching.
Therefore, pressing A will not switch to the Annotation tool , but instead, it adds a “Snap” instruction.
Use the toolbar at the top of the window to switch tools.

#### Hinting Outlines

A typical TT hinting setup.
Blue and red outlines are shown in the background.
In color, the hinting instructions overlapping the outlines are described in Instructions.

In the TrueType Instructor tool, three outlines are shown.
The outline of the current master is black.
The nodes and handles of this outline can be selected.
Nodes are shown as gray  discs instead of green  circles and blue  squares.
Extra nodes are also shown, regardless of the “View” → “Show Nodes” → “Extra Nodes” setting.

The blue outline shows the outline of the current instance _before_ TT hinting is applied.
Change the current instance by choosing from the menu next to the eye  icon located at the bottom-left of Edit View.
Click the eye icon if the instances menu does not appear to the right.

If the selected instance corresponds to the current master, no blue outline is shown.
For example, when both the Regular master and the Regular instance are currently selected, the black and blue outlines overlap and only the black outline is shown.

The red outline shows the current instance _after_ TT hinting and grid-fitting are applied according to the current rendering intent (Grayscale, ClearType, or DirectWrite) and the currently selected pixel size.
The outline is drawn with code from Microsoft and is the exact outline distortion used on Windows.
It is not shown if the glyph has no TT hints.

Note that the pixel preview in the background is only an approximate example.
Additional filtering happens between the red outline and the pixels appearing on-screen.
This filtering is subject to so many customizations (_gammas_, _color modes_, _transparencies_, …) that an exact pixel image cannot be predicted.

Toggle the display of the blue and red outlines with “Show Pixel Preview” from the context menu of Edit View.

#### Pixel Size

With the TrueType Instructor tool active, the Info box has a pixel size field.
This field contains the pixels per em value (PPM) of the pixel image preview.
The PPM is the true pixel size of the font.
For example, consider a font with 1000 UPM and a pixel size of 12 PPM.
Then, one pixel is equivalent to 1000 ÷ 12 ≈ 83 font units.

Change the pixel size by entering a new value, or use the stepper buttons to increase or decrease the size.
With the pixel size field active, press the arrow keys Up and Down to change the value.
When the field is not active, press the Period (“.”) or Plus (“+”) key to increase the size and the Comma (“,”) or Minus (“-”) keys to decrease it.

#### Hint Direction

The current hinting direction is controlled by the wavy arrow button in the Info box.
Click the button to toggle between vertical  and horizontal  hinting.
Pressing the X key also toggles between the two modes.
Vertical hints are used with horizontal stems and vice versa (see Orientation).

The hints of the other direction are shown dimmed and grayed-out in the background for reference.
They cannot be edited.

#### Hint Order

Hints are applied in chronological order.
The order is significant because hints build on top of each other.
When a hint is attached to a point on the outline, the point executes the movement implied by the hint and becomes a _touched_ point.

After all hints have been applied, the positions of all remaining _untouched_ points are interpolated between the touched points nearest in the point index order.
This is sometimes referred to as IUP, or Interpolate Untouched Points instruction.

#### Show Point Indexes

Choose “Show Point Indexes” from the Edit View context menu to label all on-curve nodes with their point index (or “point ID”).
These numbers are needed for the TTFAutohint control instructions custom parameter (see TrueType Hinting: Autohinting).

#### Hinting Preview

With the TrueType Instructor tool  active, the Preview Area moves to the right side of Edit View and shows a list (or “waterfall”) of the glyphs in Edit View set in the currently selected instance.

The list displays a preview of the hinted glyphs at each size from 8 PPM to 80 PPM.
View different preview sizes by dragging the list with the mouse cursor up and down.
This preview is also available in the Preview Panel (“Window” → “Preview Panel”).

The preview can be displayed at three scales: no scaling (1×), 2×, and 4×.
Control-click or right-click anywhere in Edit View and choose one of these scaling modes from the context menu.

#### Web Preview

Choose “Show Preview Address…” from the Edit View context menu to start a web server previewing the font similarly to the built-in Hinting Preview.
Glyphs will present a dialog window with a Web address.
Click “Copy” to copy the address.

Open the address in a web browser to see the preview page.
The Mac does not use TT hinting, so open the page on a virtualized Windows running on the Mac or another device connected to the same local network.