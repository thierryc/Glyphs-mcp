### Interpolation Applications

Interpolation axes have two use cases: static instances and variable fonts.

A static instance is a font file at a specific point in the designspace.
For example, consider a Glyphs file with a Weight axis spanning from a Thin master to a Bold master.
Then, a Thin instance is located at one end of the axis, a Bold instance is located at the other end, and a Regular instance is located somewhere in the middle of the axis.

If the Glyphs file has multiple axes, then multiple axis coordinates can be configured for each instance.
Consider a Glyphs file with a Weight and Width axis.
In that case, there may be Thin, Thin Condensed, Thin Expanded, Regular Narrow, _Semibold Condensed_, and Bold Expanded instances.

Glyphs can also _extrapolate_ static instances.
An extrapolated instance is located outside the coordinates defined by the masters, for example, an Extra Bold instance that is bolder than the Bold master.
In practice, extrapolation is difficult to control, so most font projects only make use of interpolation.

Variable fonts are font files containing information about all masters and interpolation axes, allowing the font user to pick custom locations in the designspace.

For example, for a variable font containing a Weight axis (ranging 300–900) and a Width axis (50–140), a font user might pick “SomeFont Weight=600 Width=70” instead of “SomeFont Semibold Narrow”.
This method allows picking any configuration of weight and width without the font vendor preparing static instances for every possible combination.
Variable fonts may also include static instances, offering a predefined set of axis configurations for convenient access.