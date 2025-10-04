#### Round Corners

“Filter” → “Round Corners” rounds all selected corners of a path.
The filter is only applied to outwards pointing corners if nothing is selected.
The “Radius” is defined in font units.
Choose “Visual corrections” to balance the rounding of acute and obtuse corners using smaller and larger radii, respectively.
Such visual corrections tend to create more natural-looking rounding.

From left to right:

No filter, without visual correction, with visual correction, filter applied to outwards and inwards pointing corners.

The custom parameter rule is as follows:

```filter
RoundCorner; `Radius`; `Visual Corrections`
```

If `Radius` is positive, it is applied to outwards pointing corners;
if it is negative, it is applied to inwards pointing corners.
Add multiple `RoundCorner` custom parameter filters to control both.
Set `Visual Corrections` to _{1} to enable it or _{0} to disable it.
For example, the following rule settings apply a corner radius of 55 to outwards pointing corners with visual corrections enabled:

```filter
RoundCorner; 55; 1
```

When used on a variable font setting, add the keyword `compatible` at the end to improve the compatibility of the resulting rounded outlines, like so:

```filter
RoundCorner; 55; 1; compatible
```