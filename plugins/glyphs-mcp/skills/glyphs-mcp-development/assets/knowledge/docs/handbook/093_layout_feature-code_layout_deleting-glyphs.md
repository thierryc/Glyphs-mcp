### Deleting Glyphs

Glyphs may be removed with a feature using the `delete` keyword (or its abbreviation: `del`).
Remove all occurrences of a glyph by writing its name after the `delete` keyword:

```fea
delete tonos;
```

Glyphs may also be deleted contextually.
Mark the glyph to be deleted by adding a single quote (`'`) after its name.
Define the context by writing glyph names and classes before and after the marked glyph.
In the following example, tonos is only deleted when followed by Alpha:

```fea
delete tonos' Alpha;
```

The `delete` keyword is not supported by standard AFDKO-based tools.
Alternatively, substitute a glyph by the special keyword `NULL` to delete it.
This method also works when used with AFDKO tools outside of Glyphs.

```fea
sub tonos by NULL;
sub tonos' Alpha by NULL;
```