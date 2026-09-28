"""Shared typed preparation algorithms; native access occurs only when invoked."""

class PreparationError(RuntimeError):
    pass


def set_node_name(node, name):
    """The wrapper stringifies None; Glyphs' native selector preserves nil."""
    setter = getattr(node, 'setName_', None)
    if callable(setter):
        setter(name)
    else:
        node.name = name


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
