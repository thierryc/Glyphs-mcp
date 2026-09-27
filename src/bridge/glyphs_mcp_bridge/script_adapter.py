"""Live script targets share typed-operation precision protection, without snapshots."""
from glyphs_mcp_protocol.script_targets import value
from . import outline_reads


def target(adapter, document_id, change):
    owner = adapter._target_layer(document_id, change['glyph'], change['layer'])
    layer = outline_reads.surface_layer(owner, change['surface'])
    adapter._protect_write(document_id, layer, {'kind': 'coordinates'})
    return layer, value(owner, 'undoManager')


def release(adapter, document_id, layer):
    """Release one target's transient precision state between native turns."""
    state = adapter._rounding_states.get(document_id, {}).pop(id(layer), None)
    if state is not None and not adapter._set_rounding(*state):
        from .core import BridgeError
        raise BridgeError('native_write_failed', 'Could not restore a script target rounding flag')
