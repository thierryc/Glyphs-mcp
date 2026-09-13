### Font-level Hints

TrueType hinting uses standard stem values and TT zones on each master.
Glyphs uses these font-level hints to replicate the glyph-level hints from the main master to all other masters.

#### TrueType Zones

Zones help unify the vertical alignment of shapes throughout the font.
When outlines are grid-fitted onto the screen pixels, vertical shape extrema that live in the same zone will be rounded to the same height, typically a pixel edge.
Place the zones at vertical metrics such as the baseline, descender, ascender, shoulder height, figure height, nabira height, cap height, rekha height, small caps height, or whatever else makes sense for the design.

A typical TrueType zones setup: top zones with positive sizes at ascender, cap height and x-height; bottom zones with negative sizes at baseline and descender.

By default, TT hinting uses the main alignment zones defined in “File” → “Font Info…” → “Masters” → “Metrics”.
Set up zones specific to TT hinting by adding the TTFZones custom parameter in “File” → “Font Info…” → “Masters”:

If the font already contains PostScript hinting zones, choose “Get PS zones” from the actions  menu at the bottom-left of the window to import them as TT zones.
Add additional zones with the plus  button and remove any selected zone with the minus  button.
A font can have any number of TT zones.
Zones have the following properties:

###### Name

The name identifies a zone in the list.
It can be arbitrary text, and each name must be unique.
The “xHeight” name is special: it is used for the x-height zone, which is treated differently in grid-fitting.
A zone with that name has a higher probability than other zones of rounding up at small sizes.
Names are shown in the Info box when using the TT Instructor tool and a “Snap” hint is selected.

###### Position

The position determines the emplacement of the flat edge of the zone.
The flat edge is the offset from the baseline from which the zone is extending.
Negative positions are placed below the baseline.

###### Size

The size defines the value of the flattening zone during the overshoot suppression.
A top zone has a positive size; a bottom zone has a negative size.
Top zones are meant for the top vertical extremes of shapes, like the x-height, shoulder height, cap height, or nabira height.
Bottom zones are meant for catching the bottom ends of shapes, like the baseline, the descender, or the bottoms of small figures such as numerators, inferiors, and superiors.

Ensure that the area defined by the position and the size encompasses all overshoots that are supposed to be flattened to the zone position by the rasterizer.
For instance, at the x-height, put the “Position” to the height of the lowercase x, and make sure the “Size” is large enough to catch all overshoots, like in the lowercase “o”.
This works similarly to PostScript alignment zones.

###### Alignment

Link a zone to another zone with the “Align” option.
If a zone is aligned to another, the distance between the zone positions is rounded and applied to the zone.

PPM (_pixels per em_) is a font size measurement.
See Pixel Size for details.

This will result in more consistent transitions from one PPM size to the next.
Use this for zones that are very close to each other, perhaps even overlapping, and where it may be problematic if the zones diverge too far at low-resolution pixel renderings.
Aligned zones are displayed at the same height if their distance is less than half a pixel, one pixel apart if their distance is half a pixel, and so on.

###### Deltas

(This property only applies to the main master.)
Click the delta  button to fine-tune a zone at specific PPM sizes.
A table of buttons will be shown.
The columns of the table are the masters of the font, and the rows are PPM sizes.
Click a button to switch between rounding up , down , or no rounding .
The delta  icon in the zones list is filled with the accent color if any button is set to rounding up or down.

Rounding is helpful if a zone is one pixel too low or too high at a given PPM size.
If it is too low, round it up; if it is too high, round it down.
Use the Hinting Preview to check for any zones that need to be rounded up or down.

###### Filter

(This property only applies to the main master.)
Click the globe  button to limit the zone to a subset of glyphs.
The subset is defined like a Smart Filter.
See Smart Filters for details.
The globe  icon in the stems list is filled with the accent color if any filters are set.

#### TrueType Stems

Stems help unify the displayed size of stroke thicknesses at low resolutions.
By default, TrueType hinting uses the standard stems of a master.
Define stems specifically for TT hinting by adding the TTFStems custom parameter in “File” → “Font Info…” → “Masters”.
Click the value field of the parameter to edit the stems:

If the font already contains PostScript stems, choose “Get PS stems” from the actions  menu to import them as TT stems.
Add additional stems with the plus  button and remove a selected stem with the minus  button.
The following stem properties can be edited:

###### Orientation

A hint is oriented in the X-direction  or Y-direction .
Click the double arrow icon to switch between the two orientations.

The orientation of a hint describes the direction in which its points are moved.
An X-direction  hint spans the thickness of a vertical stem.
A Y-direction  hint spans the thickness of a horizontal stem.

###### Name

The name labels the stem.
It can be arbitrary text, but it is a good idea to use descriptive names.

###### Size

The average stem thickness.
In screen rendering, similarly-sized stems will be unified and displayed with the same number of pixels.

###### Deltas

(This property only applies to the main master.)
Click the delta  button to fine-tune a stem at specific PPM sizes.
This property works like the “Deltas” of TT zones.
Note that stem deltas are only applied for ClearType-style rendering modes (also referred to as Windows GDI).

###### Filter

(This property only applies to the main master.)
Click the globe  button to limit the zone to a subset of glyphs.
This property works like the “Filter” of TT zones.

#### TrueType BlueFuzz

Use the TTFBlueFuzz custom parameter to extend all TT zones by a certain amount.
The specified amount will be added both above and below to each zone.
It defaults to 1 unit.

The parameter is helpful for testing stem values or for fixing imprecisions in interpolation:
Even if the drawings end up nicely in the zones in all masters, they may still drop out of them in interpolated instances.
Such imprecisions can occur due to rounding errors.
Test the font using the Hinting Preview to see if the zones work in all instances, and if not, increase the TTFBlueFuzz.

Add the parameter in “File” → “Font Info…” → “Font”, “Masters”, or “Exports”.
Adding it to the “Font” tab applies it to all instances equally.
If the parameter is instead added to the masters, it will be interpolated at export.
Add it to a single instance in “Exports” to overwrite the masters and font settings.