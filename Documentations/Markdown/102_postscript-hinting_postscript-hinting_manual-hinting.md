### Manual hinting

The implementation of PostScript hinting in Glyphs allows manual and automatic hints inside the same font.
Before resorting to manually inserting hints, try to get as far as possible with autohinting.
Only glyphs that do not display correctly at low resolutions will need manual intervention.

Manual and automatic hinting cannot complement each other _inside the same glyph_.
Any manually hinted glyph is excluded from the autohinting process.
Thus, when adding hints manually, the glyph must be hinted _fully_ by hand.

There are two types of glyph-level hints, stem hints and ghost hints.
Stem hints describe a vertical or a horizontal stem or stem-like feature of a glyph, like a serif or a crossbar.
Ghost hints mark the top and bottom edges when a horizontal stem hint cannot be applied.

In combination with alignment zones, horizontal ghost and stem hints are important for the vertical alignment at the vertical font metrics, like the x-height or the ascender.
At low resolutions, the rasterizer will try to vertically align the edges of all hinted horizontal stems that reach into an alignment zone.
The horizontal hints must have their _{Y} coordinates in common with the nodes that are supposed to align.
A single hint will do for all nodes it touches at its height.

Stem hints can overlap each other, for example, the vertical stem hints in the figure eight.
PostScript hinting does not allow overlapping of hints.
So, in cases like this, Glyphs will automatically insert pieces of information called hint replacement, which turns hints on or off for different parts of the glyph outline.
This handles issues related to overlapping hints.

In a Multiple Master setup, only hints in the main master will be considered.
In this case, make sure all manually set hints are linked to nodes on the outline (see Stem Hints).
See Hinting Multiple Masters for details.

In Edit View, choose “Autohint” from the context menu to get a good start.
This way, glyph-level hints will be inserted like the autohinter would have done it when the font is exported.
Edit these hints as described in the following sections.
Remember that a glyph is not automatically hinted at export if it contains manual hints so that no additional hints will be added at export.

#### Stem Hints

Add a stem hint to a glyph by choosing “Add Horizontal Hint” or “Add Vertical Hint” from the context menu.
A gray bar with a number badge  will appear.
The two numbers indicate the origin  and size  of the hint.

Adding a hint while two nodes are selected will _link_ the hint to these nodes.
Adding linked hints this way even works on multiple node pairs at once, as long as each pair is on a separate outline.
For best results, always link hints to extremum nodes (see Extremes & Inflections).

Positioning of vertical stem hints (green) and horizontal stem hints (yellow).

Select a hint by clicking its gray number badge.
Shift-click to select multiple hints.
Edit the value of the selected hint in the Info box (“View” → “Show Info”, Cmd-Shift-I).
Press Tab to select the next hint, or Shift-Tab to go to the previous one.

Edit a hint graphically by dragging the blue marks at the edges of the hint.
The blue circle  indicates the hint origin, while the triangle  shows the size and orientation of the hint.
When one of the markers is dragged onto a node, Glyphs will link the hint to the position of the node.
Moving the node will also adapt the hint.
Delete the selected hints by pressing the Delete key.

In the exported OTF file, all stem hints must have a width greater than zero.
Glyphs will automatically correct hint directions at export to turn all stem hints positive.

#### Ghost Hints

Use ghost hints to vertically align the top or bottom of a glyph when horizontal stem hints are not applicable.
For instance, consider a sans-serif uppercase “I”.
The top needs to align with the cap height zone, the bottom with the baseline zone.
In a serif “I”, horizontal hints would apply to the serifs, but the sans-serif letter lacks the horizontal features necessary for a horizontal hint.
In this case, put a top ghost hint on the top of the “I” and a bottom ghost hint at the bottom of the “I”.
Similar situations occur on the top of a sans-serif “L” and at the bottom of a sans-serif “P”:

Positioning of ghost hints (blue) alongside regular stem hints.
The ghost hints work where no horizontal hints can be applied.

Create a ghost hint by Control-clicking or right-clicking a single node and choosing “Add Horizontal Hint” from the context menu.
Turn an existing hint into a ghost hint by Control-clicking or right-clicking the coordinate badge of a hint and choosing “Make Ghost Hint”.

The badge of a ghost hint only displays the position and its orientation.
An upward arrow _{↑} a top ghost hint; a downward arrow _{↓} indicates a bottom ghost hint.
Attach it to a point by dragging the blue circle onto a node.
Set the vertical orientation of a ghost hint by selecting it and clicking the upward  or downward  icon in the Info box (“View” → “Show Info”, Cmd-Shift-I).

#### Hinting Multiple Masters

PostScript hints, like TrueType hints, need to be defined for only the main master.
By default, that is the first master in the masters list.
Set the Get Hints From Master custom parameter in “File” → “Font Info…” → “Font” (Cmd-I) to mark a different master as the main master.
Provided the hints are linked to nodes on the outline and the paths are compatible, they will be transferred to the corresponding nodes in compatible masters at interpolation time.

Manual hints in other masters will be ignored unless there are no hints in the main master.
When using Alternate or Intermediate layers, insert hints in the layer that replaces the master layer carrying manual hints.