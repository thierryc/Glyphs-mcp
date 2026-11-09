"""Filter discovery must not become a filter execution surface."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
for component in ('bridge', 'protocol', 'sidecar'):
    sys.path.insert(0, str(ROOT / 'src' / component))
from glyphs_mcp_bridge.native_filters import inventory, LIMIT, CAPABILITY


def test_identity_only_and_missing_metadata(monkeypatch):
    class Offset:
        def title(self): return 'Offset Curve'
        def filter(self, *args): raise AssertionError('must never execute')
        def processFont_withArguments_(self, *args): raise AssertionError('must never execute')
    class Rmx:
        def name(self): return 'RMX Scaler'
        def versionString(self): return '1.1.22'
    monkeypatch.setitem(sys.modules, 'GlyphsApp', NS(Glyphs=NS(filters=[Rmx(), Offset()])))
    assert inventory() == dict(available=True, truncated=False, items=[
        dict(className='Offset', displayName='Offset Curve', version=None),
        dict(className='Rmx', displayName='RMX Scaler', version='1.1.22')])


def test_absent_filters_is_valid_empty_inventory(monkeypatch):
    monkeypatch.setitem(sys.modules, 'GlyphsApp', NS(Glyphs=NS(filters=[])))
    assert inventory() == dict(available=True, items=[], truncated=False)


def test_discovery_failure_is_explicit_and_does_not_break_status(monkeypatch):
    monkeypatch.setitem(sys.modules, 'GlyphsApp', NS(Glyphs=NS()))
    result = inventory()
    assert result['available'] is False and result['items'] == []
    assert result['error']['code'] == 'filter_inventory_unavailable'


def test_inventory_is_bounded(monkeypatch):
    monkeypatch.setitem(sys.modules, 'GlyphsApp', NS(Glyphs=NS(filters=[NS()] * (LIMIT + 20))))
    result = inventory()
    assert result['truncated'] and len(result['items']) == LIMIT


def test_sidecar_negotiates_inventory_without_inventing_old_runtime_support(tmp_path):
    from glyphs_mcp_sidecar.service import SidecarService
    from glyphs_mcp_sidecar.jobs import JobStore
    bridge = NS(status=lambda: dict(readCapabilities=[]))
    service = SidecarService(bridge, jobs=JobStore(tmp_path), worker=NS(status=lambda: {}))
    service.status_cache.refresh()
    assert 'nativeFilters' not in service.get_status()
    bridge.status = lambda: dict(readCapabilities=[CAPABILITY], nativeFilters=dict(available=True, items=[]))
    service.status_cache.refresh()
    status = service.get_status()
    assert CAPABILITY in status['readCapabilities'] and status['nativeFilters']['items'] == []
