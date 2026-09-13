"""Live-instance identity tests. The recycled address is simulated, not a native observation."""
import gc
import sys
import weakref
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[3]
for name in ('protocol','bridge'):sys.path.insert(0,str(ROOT/'src'/name))
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.core import BridgeError
from test_simple_v2_glyphs_adapter import adapter


def test_known_id_reads_live_data_and_is_independent_of_frontmost():
    bridge,_=adapter();original=bridge.glyphs.fonts[0];target=bridge.list_documents()[0]['id']
    other,_=adapter();second=other.glyphs.fonts[0];second.glyphs['A'].name='other'
    bridge.glyphs.fonts.insert(0,second)
    assert bridge.read_entities(target,[{'kind':'glyph','id':'A'}],['name'])[0]['values']=={'name':'A'}
    original.glyphs['A'].name='fresh'
    assert bridge.read_entities(target,[{'kind':'glyph','id':'A'}],['name'])[0]['values']=={'name':'fresh'}
    with pytest.raises(BridgeError) as error:bridge.read_entities(target,[{'kind':'glyph','id':'missing'}],['name'])
    assert error.value.code=='target_not_found'
    assert bridge._font(target) is original


def test_closed_replaced_same_path_and_new_adapter_reject_old_ids():
    bridge,_=adapter();old=bridge.list_documents()[0]['id'];bridge._generations[old]=7
    other,_=adapter();replacement=other.glyphs.fonts[0]
    replacement.filepath=bridge.glyphs.fonts[0].filepath
    bridge.glyphs.fonts[:]=[replacement]
    with pytest.raises(BridgeError) as error:bridge._font(old)
    assert error.value.code=='document_not_found'
    assert old not in bridge._generations
    new=bridge.list_documents()[0]['id'];assert new!=old
    restarted=GlyphsAdapter(bridge.glyphs)
    with pytest.raises(BridgeError) as error:restarted._font(new)
    assert error.value.code=='document_not_found'
    assert restarted.list_documents()[0]['id'] not in (old,new)
    bridge.glyphs.fonts.clear()
    with pytest.raises(BridgeError):bridge._font(new)
    assert not bridge._ids


def test_retained_native_binding_blocks_address_reuse_until_retired(monkeypatch):
    free=[42]
    class NativeFont:
        def __init__(self):
            self.address=free.pop() if free else 43
        def __del__(self):free.append(self.address)
    monkeypatch.setitem(sys.modules,'objc',SimpleNamespace(pyobjc_id=lambda font:font.address))
    original=NativeFont();weak=weakref.ref(original)
    host=SimpleNamespace(fonts=[original]);bridge=GlyphsAdapter(host)
    stale=bridge.list_documents()[0]['id'];host.fonts.clear();del original;gc.collect()
    # Closed native object remains retained while its address -> ID entry exists.
    assert weak() is not None and 42 not in free
    replacement=NativeFont();assert replacement.address==43
    host.fonts.append(replacement)
    with pytest.raises(BridgeError):bridge._font(stale)
    gc.collect();assert weak() is None and 42 in free
    recycled=NativeFont();assert recycled.address==42
    host.fonts.append(recycled);fresh=bridge._id(recycled)
    assert fresh!=stale
    with pytest.raises(BridgeError) as error:bridge._font(stale)
    assert error.value.code=='document_not_found'
    assert bridge._font(fresh) is recycled
