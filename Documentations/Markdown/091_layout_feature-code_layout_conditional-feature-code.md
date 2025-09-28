### Conditional Feature Code

Feature code can be wrapped in `#ifdef` blocks to limit it to variable fonts.
Such a code block ends with a `#endif` line:

```fea
#ifdef VARIABLE
sub a by a.var;
#endif
```

Rules inside a `#ifdef` (if defined) block are included only in variable fonts.
Use `#ifndef` (if not defined) to include feature rules only in non-variable fonts:

```fea
#ifndef VARIABLE
sub a by a.static;
#endif
```

Variable-only blocks may contain OpenType feature variations.
These restrict substitution and positioning rules to a specific region of the designspace.
Define a feature variation by writing the `condition` keyword followed by the axis ranges to which the code following the condition should be limited:

```fea
#ifdef VARIABLE
condition 600 < wght < 900;
sub dollar by dollar.alt;
#endif
```

Axis ranges are written as the axis tag bounded by a lower and upper limit.
Write a less-than sign (`<`) between the limit value and the axis tag.
Note that, although the less-than sign is written for both the lower and upper limit, the lower limit actually behaves as if a less-than-or-equal sign (“≤”) was used.
An axis range can specify both a lower and upper limit, or only one of the two.

A condition can be restricted to multiple axis ranges.
Separate them with a comma.
The code following the condition is used only if all specified axis ranges match.

```fea
#ifdef VARIABLE
condition 600 < wght < 900, 70 < wdth < 90;
sub won by won.boldcondensed;
#endif
```