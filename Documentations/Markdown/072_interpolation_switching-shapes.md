### Switching Shapes

Some glyphs may not stay compatible as they interpolate.
Examples include the dollar sign (“$”) losing its stroke in the middle in bold weights or double-story forms switching to a single-story form at an italic angle (“a” → “_a_” and “g” → “_g_”).
There are three methods by which glyph shapes can be switched:

- using Alternate layers to switch to different glyph outlines in both static instances and variable fonts;

- replacing glyphs with other glyphs at export;

- substituting glyphs by other glyphs for certain regions of the designspace in variable fonts.

#### Alternate Layers

An Alternate layer is a layer that contains an alternate glyph outline and information about where in the designspace the glyph should switch to the alternate outline.

Alternate layers are added to individual glyphs.
For each master, select the master layer in the “Layers” palette, click the plus  button to add a new layer, Control-click or right-click the new layer and choose “Alternate” from the context menu.

After converting to an Alternate layer, number fields for the minimum and maximum coordinates will open.
These describe the designspace region in which the alternate shape should be used.
For example, consider a single Weight axis ranging from 44 to 130 where the Alternate layer should be used for a weight of 90 or greater.
In that case, set the “min” value to 90 and leave the “max” field empty.

Confirm by pressing Return.
The name of the Alternate layer is displayed in bold as comma-separated axis ranges between square brackets (for example, `[90‹wg]` or `[80‹wg, 25‹wd‹50]`).
This is why Alternate layers are also referred to as _bracket layers_.

| Axis Name | Tag | Abbr. |
|---|
| Italic  |  ital  |  it  |
| Optical Size  |  opsz  |  oz  |
| Slant  |  slnt  |  sl  |
| Width  |  wdth  |  wd  |
| Weight  |  wght  |  wg  |

Common axis names are abbreviated to two letters; the full axis tag is shown for all other axes.

Modify the outlines on the Alternate layers to fit the alternate design of the glyph.
Alternate layers do not need to be compatible with the master layers, but they do need to be compatible with each other.
The Master Compatibility view also shows Alternate layers, but they are offset by a gap:

Master Compatibility view for the dollar glyph with two masters (Thin and Black), two Intermediate layers, and three Alternate layers.
The currently active glyph layer is both an Intermediate layer and an Alternate layer.

A layer can be both an Intermediate and Alternate layer.
In that case, both the square bracket Alternate name (`[…]`) and the curly brace Intermediate name (`{…}`) are displayed in the “Layers” palette.
Double-click either one to edit its settings.

A master layer can also be designated as an Alternate layer.
For that, Control-click or right-click a master layer in the “Layers” palette and choose “Alternate”.
Configure the axis range of the master layer like a normal Alternate layer.

Then, add a new layer to the master, mark it as an Alternate layer, and leave both the “min” and “max” fields empty.
This renames the new layer to “[]”.
Place the alternate outline on the master layer and the normal outline on the “[]” layer.
Whether the master or a backup layer is converted to an Alternate layer is not relevant to the exported fonts; it is purely an organizational choice within Glyphs.

In variable fonts, Alternate layers are activated using a specific OpenType feature.
Set the Feature for Feature Variations custom parameter in “File” → “Font Info…” → “Font” to the four-letter feature tag.
By default, Glyphs uses `rlig`, but `rvrn` is also a common choice.
Different features will be processed at different stages of the text shaping process; this depends on the operating system and application displaying the text.

#### Replacing Glyphs at Export

Glyphs can be replaced by other glyphs at export for both static instances and variable font settings.
For this, two custom parameters must be added in “File” → “Font Info…” → “Exports”.

Firstly, add the Rename Glyphs custom parameter, click its value to edit it, and write one glyph swap per line.
A glyph swap is written as `someglyph=otherglyph`.
This switches the two glyphs in the exported font.
For instance, switch the dollar glyph for a simplified dollar.alt by adding the line `dollar=dollar.alt`.
List all glyphs with their replacement and confirm with “OK”.

Add the Remove Glyphs custom parameter to not just swap, but replace glyphs.
Click its value to edit it and list all alternative glyphs that now, after the swap, contain the normal glyph outlines.

#### Conditional Glyph Substitutions

Conditional substitutions allow glyphs to be replaced in variable fonts.
See Conditional Feature Code for details.

An example for the dollar → dollar.alt substitution from the examples above may look like this:

```fea
#ifdef VARIABLE
condition 80 < wght;
sub dollar by dollar.alt;
#endif
```

This replaces the dollar with the dollar.alt glyph for a weight of 80 or greater.

When exporting to both variable fonts and static instances, consider using the glyph replacement described in Replacing Glyphs at Export to mimic the conditional substitutions in static instances.