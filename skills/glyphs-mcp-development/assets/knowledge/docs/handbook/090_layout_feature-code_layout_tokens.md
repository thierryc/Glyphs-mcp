### Tokens

Tokens are pieces of code that help automate the feature code.
They dynamically insert values and glyph names into feature code, and their syntax starts with a dollar sign ($).
There are three types of tokens: _number values_, _glyph properties_, and _glyph predicates_.

#### Number Value Tokens

A number value token inserts the values defined in “File” → “Font Info…” → “Masters” → “Number Values”.
Number value tokens are written with a dollar sign followed by the number value name.

For example, the token `$padding` inserts the “padding” number value on the master of the font.
The value inserted by the token is interpolated if multiple masters exist.

Tokens also support basic arithmetic.
Wrap the name of the number value in curly braces to use plus `+`, minus `-`, times `*`, and divide `/` operators: `${padding*2}`.
The name of the number value must be placed at the start of the arithmetic expression.
Such operations can be helpful in, for example, the capital spacing `cpsp` feature:

```fea
pos @Uppercase <$padding 0 ${padding*2} 0>;
```

Hold down the Option key and click a number value token to show its computed value.

#### Glyph Property Tokens

A glyph property token is written as `${glyphName:property}` where `glyphName` is the name of a glyph and `property` is a dot-separated property path.

Properties can be metrics (`width`, `LSB`, `RSB`, `TSB`, `BSB`) and anchor positions (such as `anchors.top.x`).
Basic arithmetic is supported as in number value tokens.
For example:

```fea
# glyph positioning such as in the 'cpsp' feature
pos a.alt <${period:LSB} 0 ${period:LSB*2} 0>;
# custom mark to base positioning
pos base b <anchor
	${b:anchors.top_special.x}
	${b:anchors.top_special.y}> mark @SpecialTopMark;
```

Option-click a glyph property token to show its value.

#### Glyph Predicate Tokens

Glyph predicate tokens insert a space-separated list of glyph names.
The predicate determines the glyphs matched and inserted.
For example, `$[script == "adlam"]` expands to a list of all glyphs belonging to the Adlam script, and `$[name endswith ".star"]` expands to a list of all glyphs ending with a “.star” suffix.

When used in a feature class, predicate tokens can be written among other glyph names, like this:

```fea
period comma $[category == "Symbol"]
```

would expand to:

```fea
period comma at ampersand plus minus ...
```

Within prefixes and features, the predicate needs to be wrapped in square brackets, like this:

```fea
@Signs = [period comma $[category == "Symbol"]];
@SmallCaps = [$[case == smallCaps]];
```

The predicate can check for different aspects of a glyph:

True/False

Check whether a boolean true or false condition applies.
For example, `$[isAligned == true]`, `$[hasHints == false]`, or `$[isColorGlyph == true]`.

Numbers

Check for numeric values of the glyph.
For example, `$[countOfLayers == 3]` or `$[countOfUnicodes > 0]`.
Numbers are also used for glyph properties with a limited set of values.
For example, `$[colorIndex == 5]` (see Color Label for color numbers), `$[case == upper]` (use “noCase”, “upper”, “lower”, “smallCaps”, “minor”, or “other” for comparison), or `$[direction == 2]` (0: LTR, 1: BiDi, 2: RTL).

Strings

Match a text string with a glyph property.
For example, `$[name endswith ".sc"]`, `$[script == "balinese"]`, or `$[category == "Letter"]`.

Objects

Access nested glyph data for comparison.
For example, `$[layer.anchors.top.y > 600]`, `$[layer.maxX > 300]`, or `$["ipa" in tags]`.

Predicates can also be combined.
Write `AND` between two predicates if both need to be true.
Write `OR` if only one of the two needs to be true for the glyph to be included.
Write `NOT` before a predicate to invert it; that is, include all glyphs not matching the predicate.
If needed, use parentheses to group predicates.
For example:

```fea
$[script == "greek" AND case == upper]
$["todo" in tags OR NOT note contains "done"]
$["ipa" in tags OR ("lang" in tags AND case == lower)]
```

Glyph predicate tokens also support a special `class(...)` function that represents all glyphs contained in a feature class (`@SomeClass`).
Use it to check whether a glyph is in a given class, like this:

```fea
# all lowercase glyphs of the class @SomeClass
$[name in class(SomeClass) AND case == lower]
# the intersection of two classes
$[name in class(Narrow) AND name in class(TopMark)]
```

Option-click a glyph predicate token to show a list of all matching glyphs.