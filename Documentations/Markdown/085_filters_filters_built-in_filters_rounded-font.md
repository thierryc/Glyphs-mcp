#### Rounded Font

“Filter” → “Rounded Font” rounds the stem endings with appropriate overshoots.
For this, it uses the vertical stem metrics as defined in “File” → “Font Info…” → “Masters” → “Stems”.
The custom parameter rule is as follows:

```filter
RoundedFont; `Vertical Stem Width`
```

If a `Vertical Stem Width` argument is set, its value is used instead of the vertical stem width from the master metrics.
Such an override can be helpful when combined with the `include` and `exclude` arguments to define a different stem width for a subset of glyphs.
For example, consider three “Filter” custom parameters for an instance:

```filter
RoundedFont; exclude: f, k, t, dollar, percent
RoundedFont; 74; include: f, k, t
RoundedFont; 86; include: dollar, percent
```

Here, the glyphs f, k, t, dollar ($), and percent (%) would be processed with special `Vertical Stem Width` values.
See Filters as Custom Parameters for details on `include` and `exclude`.