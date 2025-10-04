## Interpolation

The glyph outlines drawn in Edit View belong to a font master.
Initially, a Glyphs file contains a single master named “Regular”.
If a Glyphs file contains additional masters (for example, a Thin and Bold master), this is referred to as a Multiple Masters setup.
Working with Multiple Masters allows Glyphs to export font instances not just for each master, but also between masters.

A small number of masters can result in a large number of interpolated instances.
In this example, two masters Thin and Bold are used to produce a total of six instances along a Weight axis.

An interpolation axis describes the aspect of the glyph design that changes between masters.
The most common axes are the Weight (from light to bold) and the Width (from condensed to extended), but there are many more possible interpolation axes.

A Multiple Master setup can have one or more axes.
While a single axis can be thought of as a line along which the design varies, two axes create a two-dimensional space in which every point is a possible font instance.
This space is referred to as the designspace, which may also have three or more dimensions.

Two perspectives on the three-axes designspace of ABC Arizona, the typeface in which this handbook is set.