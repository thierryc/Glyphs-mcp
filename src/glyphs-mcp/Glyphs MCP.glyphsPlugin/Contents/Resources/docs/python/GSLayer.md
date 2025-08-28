# GSLayer

Represents a layer within a glyph. Layers hold the drawing paths,
components, anchors, and metrics for a particular master or special case.

## Example

```python
layer = glyph.layers[0]
print(layer.width, layer.parent.name)
```
