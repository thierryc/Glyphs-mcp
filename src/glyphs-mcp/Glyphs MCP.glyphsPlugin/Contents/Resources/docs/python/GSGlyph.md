# GSGlyph

Represents a single glyph in a Glyphs font. Provides access to layers,
Unicode values, and assorted metadata about the glyph.

## Example

```python
glyph = font.glyphs["A"]
print(glyph.name, glyph.unicode)
```
