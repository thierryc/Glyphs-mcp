"""Shared typed preparation algorithms; native access occurs only when invoked."""

class PreparationError(RuntimeError):
    pass


def consume(iterator):
    while True:
        try:
            next(iterator)
        except StopIteration as done:
            return done.value


def stored_layers(glyph):
    """Read stored objects; Glyphs' wrapper iterator can create master layers."""
    count = getattr(glyph, 'countOfLayers', None)
    item = getattr(glyph, 'objectInLayersAtIndex_', None)
    if callable(count) and callable(item):
        for index in range(count()):
            yield item(index)
    else:
        yield from glyph.layers
