"""Actual-editor regression: Glyphs' font proxy repeats window queries per index."""
from types import SimpleNamespace

import pytest

from test_simple_v2_glyphs_adapter import adapter
from glyphs_mcp_bridge.core import BridgeError


class LiveFonts:
    def __init__(self, fonts):
        self.fonts = fonts
        self.reads = 0

    def values(self):
        self.reads += 1
        return list(self.fonts)

    def __len__(self):
        raise AssertionError('Do not enumerate the live window order for truthiness')

    def __iter__(self):
        raise AssertionError('Do not repeat the native inventory for each font')


def test_font_inventory_materializes_native_proxy_once_per_fresh_read():
    bridge, _ = adapter()
    original = bridge.glyphs.fonts[0]
    inventory = LiveFonts([original])
    bridge.glyphs = SimpleNamespace(fonts=inventory)
    assert bridge._fonts() == [original]
    assert inventory.reads == 1
    identity = bridge._id(original)
    assert bridge._font(identity) is original
    assert inventory.reads == 2
    inventory.fonts.clear()
    with pytest.raises(BridgeError) as exc:
        bridge._font(identity)
    assert exc.value.code == 'document_not_found'
    assert inventory.reads == 3
    assert not bridge._ids


def test_plain_font_collection_retains_live_document_identity():
    bridge, _ = adapter()
    original = bridge.glyphs.fonts[0]
    identity = bridge._id(original)
    assert bridge._font(identity) is original
    bridge.glyphs.fonts.clear()
    with pytest.raises(BridgeError):
        bridge._font(identity)
