### Multiple Substitution With Classes

Glyphs allows multiple substitution (one-to-many) to use classes instead of just single glyphs.
This works for both simple and contextual rules:

```fea
sub @Symbol by @SymbolLeft @SymbolRight;
sub @Left @Symbol' @Right by @SymbolLeft @SymbolRight;
```

The class that gets substituted (`@Symbol` in the example above) needs to have the same number of glyphs as the classes that it gets substituted by (`@SymbolLeft`, `@SymbolRight`).

If there is a single glyph or a class containing a single glyph on either side of the substitution rule, that glyph is repeated to match the count of the other classes in the substitution.