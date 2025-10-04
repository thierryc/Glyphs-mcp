### Anchors

Anchors are special points that fulfill multiple tasks in Glyphs.
They primarily serve as a connecting pivot for automatically aligning components, corners, caps, mark-to-base and mark-to-mark positioning, and cursive attachment.
These anchors adhere to certain naming conventions.

When an “origin” anchor is placed inside a glyph, it can align a component to a regular path node (see also Editing Paths: Aligning).

Some third-party scripts and plug-ins make use of special anchors.
Refer to their documentation for further details.

#### Adding, Editing, & Removing Anchors

Insert an anchor by Control-clicking or right-clicking the Edit View canvas and choose “Add Anchor” from the context menu.
An anchor named “new anchor” will be placed at the click position.
Its name is already selected for renaming.
After typing the new name, confirm it by pressing the Return key or clicking anywhere in the canvas.

Double-click an anchor to rename it, or select it and press Return, or select it and edit the anchor name in the Info box.

The glyph info database has default anchors associated with many glyphs.
Add these pre-defined anchors to the selected glyphs by choosing “Glyph” → “Set Anchors” (Cmd-U) or, with the Option key held down, “Glyph” → “Set Anchors for all Masters” (Cmd-Opt-U).
Delete all existing anchors and start over with “Glyph” → “Reset Anchors” (Cmd-Shift-U); hold down Option to reset the anchors across all masters.

Select an anchor by clicking the orange dot  that represents it.
Select the next or previous anchor by pressing the Tab key, or Shift-Tab, respectively.
Select multiple anchors by Shift-clicking them.
Names are only shown for selected anchors.
Select all anchors by running “Edit” → “Select All” (Cmd-A).
This command may need to be issued twice, since “Select All” will select all paths and only select all anchors and components if all available paths have already been selected.

Move an anchor like a node: either with the Select tool and mouse or arrow keys or through the coordinates in the Info box.
An anchor is diamond-shaped  if placed exactly on a metric line such as the x-height or the baseline, square  in an alignment zone, and circle-shaped  in all other cases.
Quickly duplicate an anchor by Option-dragging it.
Since anchor names must be unique inside a layer, an underscore will be added to the end of the name.
Remove all selected anchors by pressing the Delete key.

Align an anchor to one or two nodes by selecting the anchor and the nodes and choosing “Path” → “Align Selection” (Cmd-Shift-A).
See Editing Paths: Aligning for details.

#### Mark to Base Positioning

Glyphs can automatically build the `mark` (Mark to Base) feature using anchors.
The combining diacritical marks must contain underscore-anchors (for example, “_top” or “_bottom”), and the base glyph must contain matching anchors without the underscore prefix (for example, “top” or “bottom”).
Anchors with an initial underscore are displayed with a hole: diamond with hole, square with hole, circle with hole.
Combining glyph names often carry the word “comb” at the end of their names, such as acutecomb (◌́) or macroncomb (◌̄).

Combining diacritical marks have Unicode values and thus can be typed or inserted in a text.
This way, a font user can place any mark on any base letter by first typing the regular letter and then inserting the combining mark.

Alongside the `mark` feature, Glyphs will also build the `ccmp` (Glyph
Composition and Decomposition) feature if glyphs like idotless and jdotless are present.
See Implicit Features for further details.

#### Mark to Mark Positioning

Glyphs will automatically build the `mkmk` (Mark to Mark) feature if both underscore- and regular anchors are present in a combining diacritical mark.
A font user will then be able to stack any combining mark on any other combining mark carrying both anchors.

#### Cursive Attachment

Enable proper cursive attachment in Arabic typesetting by adding “exit” and “entry” anchors to the respective stroke endings and beginnings in medial, final, and initial letterforms.
The “entry” anchor of the instroke will be connected to the “exit” anchor of the preceding outstroke.
Preview cursive attachment immediately in Edit View when right to left typesetting is enabled.

#### Ligature Carets

Ligature carets define the positions where a text cursor should be placed on a ligature glyph.
In a ligature glyph, these positions are defined by special anchors on the baseline.
They must be named “caret”, followed by an underscore suffix, for example, “caret_1”, “caret_2”, …
The suffix needs to be different for each anchor because anchor names must be unique inside a glyph layer.
The numbering order is not significant and is exclusively used for differentiating anchors.

“Glyph” → “Set Anchors” (Cmd-U) will insert appropriate caret anchors in properly named ligature glyphs.
Most ligature glyphs are named with their individual glyph names joined by underscores, such as s_t or f_f_l.
For the glyph naming convention employed by Glyphs, see Names & Unicode.

At export, Glyphs will use the caret information to build so-called _{LigatureCaretByPos} instructions in the `GDEF` OpenType table.
At the time of this writing, the only known software supporting ligature caret positioning are Mac applications that make use of the Cocoa text engine.
Adobe and Microsoft apps ignore this information.

#### Contextual Mark Attachment

Make an anchor contextual by prefixing its name with an asterisk (“*”).
Select the anchor and edit the context in which it should overwrite the unprefixed counterpart in the “Anchor Context” field:

Moving the “bottom” anchor to the left in case the current glyph (sad-ar.init) is preceded by reh-ar.

The original “bottom” anchor (next to the start node) is used for mark attachment unless the glyph is in a context that matches the “Anchor Context” of “*bottom”.

The context field is located at the bottom of the Palette (“Window” → “Palette”, Cmd-Opt-P) and is shown when “View” → “Show Info” (Cmd-Shift-I) is checked.
Write OpenType feature code into the “Anchor Context” field with `*` representing the current glyph (the base glyph).
Classes and tokens may also be used in the context.

Additionally, the `&` symbol can be written in the context code as a placeholder for the mark glyph.
This is optional, but needed when the mark does not directly follow the base glyph.

Write `lookupflag ...;` before the context pattern code to specify lookup flags.
This is often useful with the `UseMarkFilteringSet` flag to limit the anchor context to a subset of marks.

Differentiate multiple context anchors by appending an arbitrary suffix to their names.
For example, the anchor “bottom” might have two context anchors: “*bottom.noon” and “*bottom.reh”, which have different anchor contexts.