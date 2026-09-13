"""Exact native layer reads; no dependency on a full layer scan or an id alias."""
from types import SimpleNamespace

import pytest

from test_simple_v2_glyphs_adapter import adapter
from glyphs_mcp_bridge.core import BridgeCore, BridgeError


class Layers:
    def __init__(self):
        self.rows = [SimpleNamespace(layerId="opaque-A", name="Regular", id="wrong-alias", width=600.125),
                     SimpleNamespace(layerId="opaque-B", name="opaque-A", width=601.375),
                     SimpleNamespace(layerId="opaque-backup", name="Regular", width=602.625),
                     SimpleNamespace(layerId="opaque-special", name="{500}", width=603.875)]
        self.visits = []

    def __getitem__(self, identity):
        self.visits.append(identity)
        # Permit names to simulate a native/proxy alias: the read must check its actual ID.
        return next((l for l in self.rows if l.layerId == identity), None) or next(
            (l for l in self.rows if l.name == identity), None)

    def __iter__(self):
        raise AssertionError("An exact layer read must not enumerate the collection")


def setup():
    native, _ = adapter()
    layers = Layers()
    native.glyphs.fonts[0].glyphs["A"].layers = layers
    return native, BridgeCore(native, lambda callback: callback()), native.list_documents()[0]["id"], layers


def test_native_layer_id_and_width_in_order_including_special_and_backup():
    native, core, doc, layers = setup()
    ids = ["opaque-special", "opaque-B", "opaque-backup", "opaque-A"]
    rows = core.read_entities(doc, [{"kind": "layer", "glyph": "A", "id": key} for key in ids], ["id", "name", "width"])
    assert [r["values"]["id"] for r in rows] == ids
    assert [r["values"]["width"] for r in rows] == [603.875, 601.375, 602.625, 600.125]
    assert layers.visits == ids
    # Operation lookup still has its prior compatibility behavior; no job hook changed.
    assert native._layer(native.glyphs.fonts[0], "A", "Regular") is layers.rows[0]


@pytest.mark.parametrize("field", ["id", "glyph"])
@pytest.mark.parametrize("bad", [None, "", 0, True, [], {}])
def test_missing_or_invalid_identity_parts_reject_before_layer_access(field, bad):
    _, core, doc, layers = setup()
    selector = {"kind": "layer", "glyph": "A", "id": "opaque-A"}
    selector[field] = bad
    with pytest.raises(BridgeError) as error:
        core.read_entities(doc, [selector], ["width"])
    assert error.value.code == "invalid_request"
    assert layers.visits == []


@pytest.mark.parametrize("field", ["id", "glyph"])
def test_omitted_identity_parts_reject(field):
    _, core, doc, _ = setup()
    selector = {"kind": "layer", "glyph": "A", "id": "opaque-A"}
    del selector[field]
    with pytest.raises(BridgeError) as error:
        core.read_entities(doc, [selector], ["width"])
    assert error.value.code == "invalid_request"


@pytest.mark.parametrize("identity", ["Regular", "{500}", "not-a-layer"])
def test_alias_and_missing_id_reject_entire_mixed_request(identity):
    _, core, doc, _ = setup()
    with pytest.raises(BridgeError) as error:
        core.read_entities(doc, [{"kind": "layer", "glyph": "A", "id": key}
                                 for key in ["opaque-A", identity]], ["id", "width"])
    assert error.value.code == "target_not_found"


def test_exact_id_wins_over_other_layers_name_and_duplicate_names():
    _, core, doc, _ = setup()
    result = core.read_entities(doc, [{"kind": "layer", "glyph": "A", "id": "opaque-A"}], ["id", "name"])
    assert result[0]["values"] == {"id": "opaque-A", "name": "Regular"}


def test_missing_glyph_is_explicit():
    _, core, doc, _ = setup()
    with pytest.raises(BridgeError) as error:
        core.read_entities(doc, [{"kind": "layer", "glyph": "missing", "id": "opaque-A"}], ["id"])
    assert error.value.code == "target_not_found"
