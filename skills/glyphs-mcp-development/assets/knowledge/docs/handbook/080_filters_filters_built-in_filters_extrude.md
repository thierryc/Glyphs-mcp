#### Extrude

“Filter” → “Extrude” will create a solid shadow offset for the shape of the glyph.
The following parameters are configurable:

“Offset”

Controls the length of the shadow in font units.

“Angle”

The direction of the extrusion in counterclockwise degrees from a right horizontal stretch.

“Don’t Subtract”

By default, the original shape will be subtracted from the extruded shape.
Suppress such a subtraction by enabling this option.

From left to right:

1 normal glyph 

2 standard extrude 

3 composition of 1 and 2 

4 “Don’t subtract” enabled

The custom parameter rule is as follows:

```filter
Extrude; `Offset`; `Angle`; `Don’t Subtract`
```

For example, to offset by 100 units at an angle of −30 degrees:

```filter
Extrude; 100; -30
```

`Don’t Subtract` is disabled by default.
Enable the option by setting its value to `1`:

```filter
Extrude; 100; -30; 1
```