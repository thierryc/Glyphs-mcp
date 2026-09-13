### Applying Filters

#### Filter Menu

Apply a filter by choosing “Filter” → “(name of the filter)”.
The filter will be applied to all selected glyphs in Font View.
In Edit View, the filter will be applied to a selection of glyphs made with the Text tool or to the current glyph with any other tool.

Filters usually affect only the currently visible layer.
Applying a filter to all masters of a glyph may therefore require re-running the filter on all other masters.
Quickly apply the last used filter by pressing Cmd-R.

#### Filters as Custom Parameters

Most filters can be applied to an instance on export using custom parameters.
However, some filters cannot be used for variable fonts as they would produce incompatible outlines.

Add a custom parameter by navigating to “File” → “Font Info…” → “Exports” → “Custom Parameters”.
Click the plus  button, choose “Filter”, and click “Add”.
A “Filter” parameter with a text field will be added to the list of custom parameters.

Write the name of the filter followed by its arguments into the text field.
Arguments are separated by semicolons (`;`).
Some argument values have a specific position in the arguments list, and some are named.
Named arguments begin with their name and a colon (`:`) followed by their value.

```filter
FilterName; value1; value2; someName: value3
```

For example, the following line would apply the `RoundCorner` filter with a radius of `15` and visual corrections activated (`1` for active, `0` for inactive):

```filter
RoundCorner; 15; 1
```

The order and meaning of arguments depend on the filter.
See Built-in Filters for details on the filters included in Glyphs.

Number value tokens can be used to dynamically insert values by writing the name of a token prefixed by a dollar sign:

```filter
RoundCorner; $roundRadius; 1
```

When used in a variable font setting, number value tokens are used to interpolate the filter values.

Limit a filter to a subset of glyphs by adding an `include` argument that lists all glyph names for which the filter should be applied:

```filter
RoundCorner; 15; 1; include: a, b, c
```

Similarly, use the `exclude` argument to apply a filter to all glyphs except for the listed glyphs:

```filter
RoundCorner; 15; 1; exclude: a, b, c
```

Spaces in filter parameters are optional and may be added to improve legibility.

Multiple “Filter” parameters can be added to a single instance.
They are applied during export in the order of the custom parameters.
“Filter” parameters get applied after the components of a glyph are decomposed.
Use a “PreFilter” custom parameter instead to run a filter before glyph decomposition.
The filter rules in the custom parameter text field are the same for “PreFilter”.
See Decomposing for more on glyph decomposition.

When applied from the “Filter” menu, many filters have an actions  button in the lower left of their dialog window.
Click the button and choose “Copy Custom Parameter”.
The custom parameter for the filter can now be pasted into an instance.
Open “File” → “Font Info…” → “Exports”, choose an instance from the sidebar, click the “Custom Parameters” heading, and paste the filter with “Edit” → “Paste” (Cmd-V).