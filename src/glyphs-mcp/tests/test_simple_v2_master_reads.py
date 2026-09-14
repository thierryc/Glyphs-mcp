"""Master selection and bounded native collection contracts; native proof is separate."""
from types import SimpleNamespace

import pytest

from test_simple_v2_glyphs_adapter import adapter
from test_simple_v2_sidecar import service
from glyphs_mcp_bridge.core import BridgeCore, BridgeError
from glyphs_mcp_protocol.reads import READ_CAPABILITIES


class Masters:
    def __init__(self, count=101):
        self.rows = [SimpleNamespace(id=f"opaque-{i}", name="Regular") for i in range(count)]
        self.visited = []

    def __len__(self):
        return len(self.rows)

    def __iter__(self):
        raise AssertionError("Do not scan/materialize the whole master collection")

    def __getitem__(self, key):
        self.visited.append(key)
        if isinstance(key, int):
            return self.rows[key]
        # Simulate a permissive native/proxy lookup; adapter must check actual ID.
        return next((m for m in self.rows if m.id == key or m.name == key), None)


def setup(count=101):
    value, _ = adapter()
    masters = Masters(count)
    value.glyphs.fonts[0].masters = masters
    document = value.list_documents()[0]["id"]
    return BridgeCore(value, lambda callback: callback()), document, masters


def page(core, document, **selector):
    return core.read_entities(document, [{"kind": "masters", **selector}], ["id", "name"])[0]["values"]


def test_pages_visit_only_selected_indices_and_complete_in_native_order():
    core, doc, masters = setup()
    first = page(core, doc)
    assert first["total"] == 101 and not first["complete"] and len(first["items"]) == 100
    assert set(masters.visited) == set(range(100))
    masters.visited.clear()
    last = page(core, doc, cursor=first["nextCursor"])
    assert last == {"items": [{"id": "opaque-100", "name": "Regular"}], "total": 101, "complete": True, "nextCursor": None}
    assert masters.visited == [99, 100]


def test_exact_opaque_ids_disambiguate_duplicate_names_and_preserve_order():
    core, doc, _ = setup()
    result = core.read_entities(doc, [{"kind": "master", "id": "opaque-1"}, {"kind": "master", "id": "opaque-0"}], ["id", "name"])
    assert [row["values"]["id"] for row in result] == ["opaque-1", "opaque-0"]


@pytest.mark.parametrize("selector", [{"kind": "master"}, {"kind": "master", "id": ""}, {"kind": "master", "id": None}, {"kind": "master", "id": 0}])
def test_missing_nonstring_or_empty_master_id_rejected(selector):
    core, doc, _ = setup()
    with pytest.raises(BridgeError) as error:
        core.read_entities(doc, [selector], ["id", "name"])
    assert error.value.code == "invalid_request"


@pytest.mark.parametrize("identity", ["Regular", "missing"])
def test_alias_and_unknown_id_reject_whole_mixed_request(identity):
    core, doc, _ = setup()
    with pytest.raises(BridgeError) as error:
        core.read_entities(doc, [{"kind": "master", "id": "opaque-0"}, {"kind": "master", "id": identity}], ["id"])
    assert error.value.code == "target_not_found"


@pytest.mark.parametrize("limit", [0, 101, -1, True, 1.5, "100", None])
def test_invalid_page_limits(limit):
    core, doc, _ = setup()
    with pytest.raises(BridgeError) as error:
        page(core, doc, limit=limit)
    assert error.value.code == "invalid_request"


def test_page_cannot_expand_bound_by_mixing_or_repeating_selectors():
    core, doc, _ = setup()
    for selectors in [[{"kind": "masters"}] * 2, [{"kind": "masters"}, {"kind": "master", "id": "opaque-0"}]]:
        with pytest.raises(BridgeError) as error:
            core.read_entities(doc, selectors, ["id"])
        assert error.value.code == "invalid_request"
    with pytest.raises(BridgeError):
        core.read_entities(doc, [{"kind": "master", "id": "opaque-0"}] * 101, ["id"])


@pytest.mark.parametrize("change", ["append", "boundary", "document"])
def test_cursor_rejects_changed_count_boundary_or_document(change):
    core, doc, masters = setup()
    cursor = page(core, doc)["nextCursor"]
    if change == "append":
        masters.rows.append(SimpleNamespace(id="another", name="Regular"))
    elif change == "boundary":
        masters.rows[99].id = "different"
    else:
        cursor["documentId"] = "another-document"
    with pytest.raises(BridgeError) as error:
        page(core, doc, cursor=cursor)
    assert error.value.code == "stale_master_cursor"


@pytest.mark.parametrize("cursor", [0, {}, {"offset": 100}, {"documentId": "a", "offset": True, "total": 101, "afterId": "b"}])
def test_malformed_cursor_rejected(cursor):
    core, doc, _ = setup()
    with pytest.raises(BridgeError) as error:
        page(core, doc, cursor=cursor)
    assert error.value.code == "invalid_request"


def test_empty_and_unsaved_dirty_fonts_read_without_source():
    core, doc, masters = setup(0)
    font = core.adapter.glyphs.fonts[0]
    font.filepath = None
    font.parent.hasUnautosavedChanges = lambda: True
    assert page(core, doc) == {"items": [], "total": 0, "complete": True, "nextCursor": None}
    assert masters.visited == []


def test_page_fields_and_parameters_are_explicit():
    core, doc, _ = setup()
    with pytest.raises(BridgeError) as error:
        core.read_entities(doc, [{"kind": "masters"}], ["unsupportedMetric"])
    assert error.value.code == "unsupported_read"
    with pytest.raises(BridgeError) as error:
        page(core, doc, id="unexpected")
    assert error.value.code == "invalid_request"


def test_only_reachable_advertised_bridge_capabilities_reach_sidecar_status(tmp_path):
    value, bridge, _ = service(tmp_path)
    assert value.get_status()["readCapabilities"] == []
    bridge.status = lambda: {"protocol": 1, "readCapabilities": list(READ_CAPABILITIES)}
    assert value.get_status()["readCapabilities"] == list(READ_CAPABILITIES)
    def unavailable():
        raise ConnectionError("stopped")
    bridge.status = unavailable
    assert value.get_status()["readCapabilities"] == []
