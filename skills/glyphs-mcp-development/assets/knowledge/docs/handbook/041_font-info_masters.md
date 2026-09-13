### Masters

A master is a set of specifically designed and configured glyph outlines and metrics.
From the master setup in a Glyphs file, font instances are calculated and exported as OpenType font files.
See Font Info: Exports for details.

#### Managing Masters

When a new Glyphs file is created, the font has one Regular master.
At the bottom of the “Masters” tab are buttons for adding and deleting masters.
Click the plus  button to add a new master using one of the following options:

“Add Master”

adds a new, empty master.
All glyph layers are empty, and the metrics are set to their default values.

“Add Other Font”

shows a list with all masters of the fonts currently open in Glyphs.
Select one or more masters and import them by clicking “OK”.
Click “Cancel” to not import any masters.

“Duplicate Selected”

duplicates the masters that are currently selected in the “Masters” tab.
The new masters will have the same name, glyph layers, and metrics as the selected masters.
Consider renaming the duplicate masters to distinguish them from the original masters.

Click the minus  button located in the bottom-left of the Font Info window to delete the selected masters.

Reorder masters by dragging them to the desired position in the masters list.
The first master in the list has special relevance for glyph-level hinting information (unless the Get Hints From Master parameter is set).
See Manual hinting and TrueType Hinting.

Master properties such as the name, metrics, and custom parameters can also be edited for several selected masters at once.
Properties that do not share a common value are indicated with a gray “Multiple Values” text.

#### General

In “File” → “Font Info…” → “Masters” → “General”, define the name of a master and its icon.
The master name is only used internally by Glyphs and not by exported font files.
Use instances to define the exported font files.

The master icon can be a glyph from the font or one of 25 predefined lowercase n glyphs in various widths or weights.
Click the master icon to choose a predefined image, or write a glyph name into the text field at the bottom of the icon picker to use that glyph as the icon.

#### Axes Coordinates

The “Axes Coordinates” indicate the position of a master in the designspace.
The designspace is defined by the axes in the “Font” tab.
For example, a font with two axes—width and weight—has a two-dimensional designspace.
A master can then be placed anywhere within that designspace.
See Setting up Masters for details on placing masters in a designspace.

#### Metrics & Alignment Zones

Master metrics define the baseline of the font, offsets from that baseline, and other values such as the angle of slope of italic glyphs.
In Edit View, the metrics are displayed as orange alignment lines (when “View” → “Show Metrics” is selected).
The default metrics are set according to the script and language selection.
For example, Latin fonts have the following default vertical metrics:

Ascender

The height reached by the ascenders of letters such as b, d, f, h, k, l, þ, or ß.

Cap Height

The height of capital letters such as H, T, or W without overshoot.

x-Height

The height of short lowercase letters such as x, a, c, e, n without overshoot.

Baseline

The position on which letters are placed, always 0.

Descender

The depth reached by descending letters such as Q, g, j, þ, or q.
This value is negative since it is below the baseline.

Italic Angle

The angle of slope of the italic glyphs stems.
This value affects several elements, including the sidebearings calculation, the anchors alignment between selected nodes, and transformations that take the italic angle into account.
The value is in degrees clockwise.

Other scripts use different default metrics.
For example, an Arabic font has the default metrics of _Ascender_, _Baseline_, _Descender_, _Alef Height_, _Joining Line_, and _Meem Depth_.

Click the name of a metric to edit its category, name, and scope.
The category is the metric type, and the name can be chosen freely to identify the metric.
The scope limits the metric to a subset of glyphs.
For example, scoping a metric to glyphs with a Devanagari script hides its alignment line in all other glyphs.
See Smart Filters for details on glyph scopes.

The left number field of a metric defines the offset from the baseline.
(The “Italic Angle” metric has one field only.)
The right number field is the size of the alignment zone and starts at the offset of the metric.
Nodes and anchors placed in alignment zones are highlighted.
See Nodes in Alignment Zones and Adding, Editing, & Removing Anchors.

Alignment zones are used by the automatic hinting process, which ensures that overshoots snap to even metric lines at small font sizes or low screen resolutions.
See Alignment Zones for details on PostScript hinting with alignment zones.
For TrueType hinting, separate zones may be configured (see TrueType Zones).

#### Stems

Font designs typically conform to standard stems.
For example, the capital I has a vertical stem, and the capital H has two vertical stems and one horizontal stem.
A rounded shape like the letter O has left and right vertical stems and top and bottom horizontal stems.
Serifs and crossbars, such as in the lowercase f and t, are also stems.

Frequently used stem widths are defined in “File” → “Font Info…” → “Masters” → “Stems”.
The autohinter uses these stem values to add hints to vertical and horizontal stems.
See PostScript Hinting: Autohinting for details on hinting with the autohinter.
For TrueType hinting, separate stems may be configured.

Click the plus  button located to the right of the “Stems” heading to add a new stem definition.
A stem can either be vertical  (measured left to right) or horizontal  (measured top to bottom).
The name of a stem is used to describe it and for interpolation:
When interpolating between masters, stems with the same name in both masters are used to interpolate the in-between stem value.
The stem value should be as close to as many master stems as possible.
See PostScript Hinting for more information on good stem values.

Click the actions  button located on the right of a stem entry line to restrict it to a specific subset of glyphs.
This scoping works the same as in master metrics or Smart Filters.

#### Custom Parameters

Masters can have custom parameters, just like the “Font” tab (see Font: Custom Parameters).
A custom parameter value is interpolated if it is defined in all masters.
Some custom parameters exist on the font and the master level.
A parameter on a master will overwrite such a font parameter.
Instances can also have custom parameters, which overwrite both font and master parameters.

#### Number Values

Tokens can use Number Values in OpenType feature code to insert numbers that interpolate between masters.
Click the plus  button located to the right of the “Number Values” heading to add a new number value.
See Number Value Tokens for more information.