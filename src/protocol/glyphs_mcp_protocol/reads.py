"""Additive read capabilities; tool and wire protocol versions stay unchanged."""

READ_CAPABILITIES = ("master.read.exact.v1", "masters.list.v1", "layer.read.exact.v1",
                     "selection.nodes.native.v1", "selection.context.v1", "document.context.v1", "glyphs.list.v1", "layers.list.v1", "kerning.groups.v1", "kerning.pairs.v1", "master.properties.v1")
READ_CAPABILITIES += ("paths.list.v1", "path.geometry.v1")
READ_CAPABILITIES += ("features.read.v1", "instances.read.v1")
MASTER_PAGE_LIMIT = 100
MASTER_AXIS_LIMIT = 32
MASTER_AXIS_ITEMS_LIMIT = 256
SELECTION_NODE_LIMIT = 64
SELECTION_NODE_MAX = 256
CONTEXT_GLYPH_LIMIT = 100
GLYPH_PAGE_LIMIT = 100
LAYER_PAGE_LIMIT = 100
KERNING_PAGE_LIMIT = 100
KERNING_SCAN_LIMIT = 256
PATH_PAGE_LIMIT = 100
PATH_NODE_PAGE_LIMIT = 256
FEATURE_BLOCK_PAGE_LIMIT = 100
INSTANCE_PAGE_LIMIT = 100
