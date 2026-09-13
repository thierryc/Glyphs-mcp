#### Offset Curve

“Filter” → “Offset Curve” changes the thickness of stems horizontally and vertically.
The following parameters are configurable:

“Horizontal”, “Vertical”

Define the horizontal and vertical offset from the current outline.
Positive values expand the outline; negative values contract the outline.
Click the lock  button to use the horizontal field for both values.

“Make Stroke”

Offsets the outline in both directions to form a stroke along the outline.
This is useful for creating outlines from closed paths.
See Creating Strokes for creating non-destructive strokes.

“Auto Stroke”

Offsets the outline in both directions while maintaining the vertical dimensions intact when making a stroke.
If enabled, it assumes a position of 50 %.

“Position”

Controls the distribution of the stroke.
0 % places the stroke to the left of the path, 100 % places it to the right.
At 50 %, the stroke is evenly distributed along the path.

From left to right:

“Make Stroke” with “Position” of 100 %, 50 %, 0 %, and 0 % with “Keep Compatible” enabled.

“Keep Compatible”

Keeps the offset curve compatible across masters by not introducing any new nodes or handles.
Enabling this option might reduce the offset accuracy.

Cap Style

Defines the stroke endings style when making a stroke from an open path.
Choose from flat , square , round , round inset , and aligned to the vertical and horizontal axes .

The custom parameter rule is as follows:

```filter
OffsetCurve; `Horizontal`; `Vertical`; `Make Stroke`; `Position`; `Keep Compatible`; cap:`Cap Style`
```

The `Horizontal` and `Vertical` offsets are in font units.
`Make Stroke` is _{0} for false or _{1} for true.
`Position` is either a percentage (for example, _{0.5} for 50 %) or “auto” for the “Auto Stroke” option.
Set `Keep Compatible` to “keep” to enable the option or leave the argument off to disable it.
`Cap Style` is _{1} for round, _{2} for round inset, _{3} for flat, _{4} for aligned to axes, and _{0} or left off for flat.
For example, for a stroke with thickness 20 (10 units on either side) and a cap style of round:

```filter
OffsetCurve; 10; 10; 1; 0.5; cap:1
```

Curves can be offset non-destructively using stroke styles.