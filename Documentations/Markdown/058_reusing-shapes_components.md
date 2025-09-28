### Components

Components are glyphs used as shapes inside other glyphs.
For example, the A glyph can be reused to build the “Ä”, “À”, “Â”, “Ã”, “Å”, and many more glyphs.
Diacritics like ◌̈, ◌̀, ◌̂, ◌̃, and ◌̊ can also be used as components so that other characters like “Ö”, “È”, “Ĉ”, “Ñ”, “Ů”, and many more can be formed.

The original glyph from which a component is derived is referred to as the _base glyph_ of the component.
A glyph that is built out of components is referred to as a _compound_ or _composite glyph_.
Changing a base glyph also changes all of its copies as a component.
When changing a base glyph in Edit View, all related components will update live to reflect the newly made changes.

On export, components are decomposed to paths with the “Remove Overlaps” option selected.
TrueType flavor fonts without the “Remove Overlaps” option active (such as variable fonts) keep non-overlapping components while decomposing overlapping components.
Set the Keep Overlapping Components custom parameter on an instance to also keep overlapping components in TrueType flavor fonts.

#### Building Composites

When adding a new composite glyph, Glyphs will automatically add the necessary components.
For example, adding an eacute (“é”) glyph to a font will automatically build it with an e component and an acutecomb (◌́) component.
Glyphs uses the glyph info database to figure out which components to insert into which glyphs.
This automatic insertion does not work if any of the required components do not exist in the font.

Convert an existing glyph to a composite by choosing “Glyph” → “Create Composite” (Cmd-Ctrl-C).
This command will replace all paths and components already present on the current layer.
Hold down the Option key to apply the command to all masters of the glyph (Cmd-Opt-Ctrl-C).

Add components by name or Unicode value by choosing “Glyph” → “Add Component” (Cmd-Shift-C).
Hold down Option to add the component on all masters (Cmd-Opt-Shift-C).
The component picker works the same as the glyph picker used to insert glyphs in Edit View.
See Text Tool for details.

#### Turning Paths into Components

Create a new component by selecting paths and components on a glyph layer and choosing _Component from Selection_ from the context menu or the “Glyph” menu.
A dialog window appears, prompting for the glyph name of the new component.
Glyphs will suggest a component name based on context, but the name can be changed to any other name as well.
Prefix the name of a component with an underscore (“_”) if the component should only be used inside the Glyphs file and not be part of the exported glyphs.
See also the exports glyph property.

Confirm the dialog with “OK”.
Glyphs adds the newly created component to the current Edit View tab and activates it.
The previously selected shapes will be replaced by the component.

#### Recipes

When adding glyphs to a font using “Glyph” → “Add Glyphs…”, recipes can be used to define which components should be used in which glyphs.
A recipe is a formula of glyph names that is used to create a new glyph.
The following recipe formulas can be used:

- `component`=`glyph`, for example, “Eth=Dtail”, which adds the Dtail glyph with the Eth as a single component.

- `base`+`mark`=`glyph`, for example, “x+acutecomb=xacute”, which adds multiple components (separated by a plus sign) to a new glyph. The mark glyphs are automatically aligned to the base glyph using anchors.

- `base`+`base`=`glyph`, for example, “d+ezh.connect=dezh”. Adding multiple base components to a glyph can be useful when building ligatures.

#### Editing Components

Click to select a component.
When dragging with the Select  tool, components are ignored unless the Option key is held down.
Press the Tab key to select the next component, or Shift-Tab to select the previous one.
When paths are present on a layer, the first “Edit” → “Select All” (Cmd-A) selects paths only.
Press Cmd-A once again to also select all components on the layer.

With one or multiple components selected, a component Info box appears next to the glyph Info box.
See Edit View: Info Box for details on the component Info box.

Transform components using the Info box, the bounding box, or the Palette.
Flipping a component vertically switches its “top” and “bottom” anchors to be again on top and bottom of the component.
This anchor switch is helpful, for example, when building the gcommaaccent (“ģ”) from a g and a flipped commaaccentcomb (◌̦).

Move a selected component with the mouse or the arrow keys.
Auto-aligned components can either be moved along the vertical axis or not at all.
See Automatic Alignment for details.
When moving with the arrow keys, hold down Shift for increments of 10 and Command for increments of 100.
Option-drag a component to duplicate it.
Delete all selected components by pressing the Delete key.

#### Moving between Base Glyphs and Composites

Double-click a component to edit its glyph.
The component glyph will be placed next to the composite glyph in Edit View and activated for immediate editing.
Alternatively, click the arrow  button located in the top-left of the component Info box to edit its glyph.
(For the Info box to be shown, the component must be selected and “View” → “Show Info” must be checked.)

Show all glyphs that use the current glyph as a component by Control-clicking or right-clicking the canvas and choosing “Show all glyphs that use this glyph as a component” from the context menu.

#### Component Placeholders

Component placeholders indicate a problem with a component.
There are three types of problems.

An empty base glyph placeholder is shown if the glyph layer of a component is empty.
Remove the component or fill the glyph layer.

When no base glyph is shown, the component references a glyph that does not exist (or no longer exists).
Remove the component or add the referenced glyph to the font.
Click the placeholder to see the referenced glyph name in the Info box (Cmd-Shift-I).

A bad reference indicates a circular reference, where the component contains a composite glyph that contains that component.

#### Anchors

Glyphs uses anchors for OpenType features (such as mark-to-base positioning and cursive attachment, see Edit View: Anchors) and for arranging components.
Often, the same anchors can be used for both features and for arranging components.

Unicode defines base characters like “S” (U+0053) and combining marks like ◌̌ (U+030C).
Typing a base character followed by a combining mark will place the mark on the base glyph using the anchors.
But Unicode also contains precomposed characters like “Š” (U+0160).
Glyphs for these characters can be built by using the base and mark glyphs as components.

For example, a mark component with a “_top” anchor snaps onto the “top” anchor of a base component just like mark-to-base positioning would place a mark glyph atop a base glyph.
See Adding, Editing, & Removing Anchors for general information on working with anchors.

In some situations, a component might need multiple anchors of the same type.
For example, it is common to use such alternative “top” anchors for Vietnamese diacritics.
Alternative anchors share the name of the original anchor but use an underscore suffix for differentiation.
So, there might be a “top” and a “top_alt” or “top_viet” anchor on the same glyph layer.
The suffix after the underscore can be chosen freely.

Switch between anchors by selecting an attached component and picking a different anchor from the anchor menu in the component Info box.
Show the Info box with “View” → “Show Info” (Cmd-Shift-I).
The anchor icon is only visible if multiple anchors are available.

#### Automatic Alignment

Glyphs built entirely from components are called composite or compound glyphs and can use automatic alignment to keep their metrics in sync with their base glyph.
For example, changing the left sidebearing of the U glyph would automatically adjust the glyphs “Ú”, “Ù”, “Ŭ”, “Ü”, “Ū”, and all other composite glyphs built with the U component.

Automatic alignment is enabled by default if a glyph layer contains only component shapes (no path shapes).
Control-click or right-click an auto-aligned component and choose “Disable Automatic Alignment” from the context menu to place the components manually.
Choose “Enable Automatic Alignment” from the context menu on a component to enable it again.
Automatic alignment can also be disabled for the entire font in “File” → “Font Info…” → “Other” → “Disable Automatic Alignment”.
See also Disable Automatic Alignment.

Auto-aligned components are shown in green to differentiate them from normal, gray components.
If a component has the category Number (for example, the glyphs zero–nine) and it is the only component in a composite glyph, it is shown in blue and can be shifted vertically while staying auto-aligned horizontally.

Metrics keys cannot be used for auto-aligned composite glyphs, since the sidebearings are derived from the base components.
There is one exception: auto-aligned composite glyphs can add to and remove from the automatic sidebearing values using the `=+` and `=-` operators.
For more information, see Metrics Keys & Automatic Alignment.

Automatic alignment is typically for single components, a base component with one or more mark components, or multiple base components.
These three setups are described in more detail in the following sections.

##### Single Component

A composite glyph may use a single auto-aligned component.
This setup is helpful for glyphs that look the same but should still be encoded as two separate glyphs.
That might be the case with Greek, Latin, and Cyrillic capital letters sharing the same outlines, such as Alpha/A/A-cy, Beta/B/Ve-cy, and Rho/P/Er-cy.
These glyphs belong to different scripts and may use separate kerning groups, so they should be encoded as separate glyphs instead of a single glyph with multiple Unicode values.

A single component might also be handy when constructing the glyph nine as a flipped six.
As mentioned above, such a component will be shown in blue and can be shifted vertically while keeping the automatic horizontal alignment.

Punctuation marks such as “‹” and “›”, “¿” and “?”, “{” and “}”, and arrows such as “←” and “→” can also often be built from a single flipped component.

##### Base Component & Mark Components

Build precomposed glyphs such as “Ú”, “Ù”, “Ŭ”, “Ü”, “Ū” from a base component (U in this case) and diacritical marks.
First, add the base component, followed by combining mark components.
For example, for Uacute (“Ú”), add the U component and then the acutecomb (◌́) component.
If the glyph is known to the glyph info database—as is the case with Uacute—choose “Glyph” → “Create Composite” (Cmd-Ctrl-C), and all required components will be added in the correct order.

Use anchors to place marks atop, below, or over the base component.
See Components: Anchors for details.
When adding multiple combining marks to a composite glyph, marks stack in the order in which they are added.
For this to work, mark glyphs need to contain both a base attachment anchor (such as “_top”) and a mark attachment anchor (such as “top”).
Rearrange marks using the “Shape Order” filter (see Shape Order).

Mark components positioned with anchors do not affect the sidebearings of the composite glyph.
For example, placing a macroncomb (◌̄) atop an idotless (“ı”) may result in the macron reaching outside the glyph box of the imacron (“ī”).
In such a case, either design a narrower macron and use that for the imacron or add additional space to the sidebearings of the composite glyph (see Metrics Keys & Automatic Alignment).

See the Diacritics tutorial for a guided introduction to working with diacritics.

##### Multiple Base Components

A composite glyph may also contain multiple base components.
They are placed next to each other as if they were typed together.
Combining marks can be placed on each one of the base components individually;
place a base component first, then all of its marks, then the next base component followed by its marks.

Adding multiple base components to a composite glyph is handy when building ligature glyphs.
Using components for ligatures is particularly helpful for scripts like Arabic that make extensive use of ligatures.

Base components can be connected using the same anchors that are used for cursive attachment.
This technique can build an n glyph from a _part.stem and a _part.arch component, where the _part.stem has an “#exit” anchor and _part.arch has an “#entry” anchor.
Add both components to the n glyph, and they will connect such that the exit and entry anchors overlap.
Add an “#exit” anchor to the _part.arch to build an m composite glyph from a _part.stem and two _part.arch components.
See Underscore Components for details on working with components with a name beginning with an underscore.

#### Locking Components

Lock components that are not automatically aligned by Control-clicking or right-clicking it and choosing “Lock Component” from the context menu.
Locked components cannot be moved.
Unlock a component by choosing “Unlock Component” from the context menu.

#### Decomposing

Convert all components inside a glyph to paths by choosing “Glyph” → “Decompose Glyph” (Cmd-Shift-D).
All components, including all nested components, will be decomposed into their paths and anchors.

Choose “Decompose” from the context menu on a component to only decompose the selected components.
In this case, nested components will not be decomposed.

#### Combining Paths and Components

As soon as there is a path on a layer, automatic alignment is disabled.
Therefore, be careful when combining components and paths because shifts may occur, especially if the base glyph of the component is changed.
Instead, consider building the glyph from components only and connecting them with anchors as outlined in Components: Anchors, thus enabling automatic alignment.
Consider defining glyphs as non-exporting if they are only ever used as parts of other glyphs.
See Underscore Components and Smart Components for working with non-exporting components.

When dragging an element, such as a node or an anchor, the nodes inside components are highlighted.
Dragging an element near such a highlighted point snaps it to the position.

Choosing “Path” → “Align Selection” (Cmd-Shift-A) while exactly one point and one component are selected will align the origin point of the component to the selected node.
The node keeps its position.
The origin point is where the baseline crosses the left sidebearing if the italic angle is zero.
If the component glyph contains an “origin” anchor, it is used as the origin position instead.

#### Nesting Components

Glyphs allows components to be nested.
For example, the dieresiscomb (◌̈) can be built from two dotaccentcomb (◌̇) components and then be used as a component in glyphs such as edieresis (“ë”).

“top” and “bottom” anchors propagate from a component to the glyph in which the component is placed.
For example, consider a glyph E that has a “bottom” anchor.
When a composite glyph, like Edieresis (“Ë”), uses E as a component, it inherits the “bottom” anchor from the E.
That way, bottom marks such as circumflexbelowcomb (◌̭) can attach to the bottom of Edieresis, even though it itself does not contain a “bottom” anchor.
Propagated anchors are overwritten by anchors in the composite glyph.
Continuing the example, if the Edieresis glyph had its own “bottom” anchor, then that would overwrite the “bottom” anchor of the E component.

Add a Propagate Anchors custom parameter to the “Font” tab in “File” → “Font Info…” with its checkbox unselected to prevent anchor propagation.

#### Preferred Marks for Glyph Composition

When automatically building composites, Glyphs prefers marks with the same name suffix as the composite.
For instance, when composing agrave.sc, Glyphs prefers a mark glyph named gravecomb.sc over gravecomb if such a glyph exists.
When building uppercase letters, marks with a “.case” suffix are preferred.
For example, when building the Agrave glyph, Glyphs will use the mark gravecomb.case—if it exists—over gravecomb.
This is helpful when the “.case” diacritical marks are flattened to accommodate the limited vertical space available in the uppercase letters.
The glyphs i and j are built from idotless and jdotless with a dotaccentcomb.
When building composite glyphs based on i and j—such as imacron (“ī”) or jcircumflex (“ĵ”)—Glyphs prefers mark glyphs ending in “.i” or “.narrow”.

#### Underscore Components

By default, a glyph whose name starts with an underscore is not exported.
This allows for glyphs solely used as components in other glyphs.
Such glyphs might help to create ligature glyphs.
For example, both glyphs fl and f_f may use an _f.connect component for the first “f”.