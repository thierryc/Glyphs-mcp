### Vector Drawing Applications

Glyphs supports pasting outlines from most vector drawing applications.
The pasted outline may be placed far outside the glyph box.
Glyphs detects such situations and offers to correct the bounds of the pasted outline:

The following sections describe recommended setups for specific applications.

#### Adobe Illustrator

Tip:

Quickly get the correct scale by drawing a rectangle with the height of the capital letters in Glyphs, copy and paste it into an Illustrator artboard and scale the drawings to fit the height of the rectangle.

Vector outlines can be imported from Illustrator with copy and paste.
For best results, configure the Illustrator artboard such that one point corresponds to one font unit.
A font with 1000 UPM would map to an Illustrator artboard 1000 pt high.

Copy closed paths in Illustrator and paste them with “Edit” → “Paste” (Cmd-V) in Glyphs onto the current glyph.
Node coordinates are rounded unless the grid spacing of the font is zero.

#### Affinity Designer

Affinity Designer places the copied outlines at the origin (0, 0), regardless of where the outline is placed in the Designer artboard.
Glyphs supports both the standard outline copying mode and the SVG mode (“Affinity Designer” → “Settings…” → “General” → “Copy items as” → “SVG”).

#### Sketch

In Sketch, set the contour to a 1 pt outline without fill.
This will prevent double outlines in Glyphs.