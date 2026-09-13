#### Hatch Outline

“Filter” → “Hatch Outline” creates hatched glyphs.
The following parameters are configurable:

“Origin”

Defines the origin point (_{X} and _{Y} coordinates) where the hatching pattern begins.

“Step Width”

The distance between the strokes.

“Angle”

The angle at which the strokes are drawn.
0° is horizontal, 90° is vertical.

“Offset Path”

The thickness of the strokes.
Disable this option to create open paths instead (which may be useful in combination with other filters or plug-ins).

The custom parameter rule is as follows:

```filter
HatchOutlineFilter; OriginX:`X`; OriginY:`Y`; StepWidth:`Distance`; Angle:`Angle`; Offset:`Offset`
```

The arguments are all optional and can be written in any order.
If left out, the argument of an option will assume its default value.
For instance, for strokes, a thickness of 5 inclined at a 40° angle and placed at every 20 units:

```filter
HatchOutlineFilter; StepWidth:20; Angle:40; Offset:5
```

The hatch origin will default to `X` = _{0}, `Y` = _{0}.