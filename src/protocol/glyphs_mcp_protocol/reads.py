"""Additive read capabilities; tool and wire protocol versions stay unchanged."""

READ_CAPABILITIES = ("master.read.exact.v1", "masters.list.v1", "layer.read.exact.v1",
                     "selection.nodes.native.v1", "selection.context.v1", "document.context.v1")
MASTER_PAGE_LIMIT = 100
SELECTION_NODE_LIMIT = 64
SELECTION_NODE_MAX = 256
CONTEXT_GLYPH_LIMIT = 100
