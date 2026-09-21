"""Bounded exact path inventory, nodes and segment geometry."""

from pathlib import Path
from types import SimpleNamespace as NS
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
for part in ("protocol", "bridge"):
    sys.path.insert(0, str(ROOT / "src" / part))

from glyphs_mcp_bridge.core import BridgeError  # noqa: E402
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter  # noqa: E402
from test_simple_v2_outline_edit import Collection, Layer  # noqa: E402


def adapter():
    layer = Layer("M0"); glyph = NS(name="y", id="g-y", layers=Collection([layer]))
    document = NS(isDocumentEdited=lambda: True, changeCount=lambda: 7, undoManager=lambda: None)
    font = NS(glyphs={"y": glyph}, masters=Collection([NS(id="M0")]), filepath=None,
              familyName="Dirty", parent=document, currentTab=None)
    value = GlyphsAdapter(NS(fonts=[font]))
    return value, value.list_documents()[0]["id"], layer


def test_dirty_unsaved_font_supports_path_segment_and_node_reads():
    value, document, _ = adapter()
    paths = value.read_entities(document, [{"kind": "paths", "glyph": "y", "layer": "M0"}], ["items"])[0]["values"]
    assert paths["complete"] and paths["items"][0]["nodeCount"] == 5
    nodes = value.read_entities(document, [{"kind": "path", "glyph": "y", "layer": "M0", "index": 0,
                                            "limit": 2}], ["nodes"])[0]["values"]
    assert len(nodes["nodes"]) == 2 and not nodes["complete"] and nodes["nextCursor"]
    segment = value.read_entities(document, [{"kind": "segment", "glyph": "y", "layer": "M0",
                                              "path": 0, "endNode": 4}],
                                  ["type", "startNode", "endNode", "points", "length", "pathHash"])[0]["values"]
    assert segment["type"] == "line" and segment["startNode"] == 3 and segment["endNode"] == 4
    assert segment["length"] == pytest.approx(((579.061-95.061)**2+(1-970)**2)**.5)
    assert segment["pathHash"] == paths["items"][0]["pathHash"] == nodes["pathHash"]


def test_path_node_cursor_is_stale_after_geometry_change():
    value, document, layer = adapter()
    first = value.read_entities(document, [{"kind": "path", "glyph": "y", "layer": "M0", "index": 0,
                                             "limit": 2}], ["nodes"])[0]["values"]
    layer.paths[0].nodes[0].position = (1, 2)
    with pytest.raises(BridgeError) as error:
        value.read_entities(document, [{"kind": "path", "glyph": "y", "layer": "M0", "index": 0,
                                        "limit": 2, "cursor": first["nextCursor"]}], ["nodes"])
    assert error.value.code == "stale_path_cursor"


@pytest.mark.parametrize("selector,fields", [
    ({"kind": "paths", "glyph": "y", "layer": "M0", "extra": True}, ["items"]),
    ({"kind": "path", "glyph": "y", "layer": "M0", "index": -1}, ["nodes"]),
    ({"kind": "segment", "glyph": "y", "layer": "M0", "path": 0, "endNode": 4}, ["script"]),
])
def test_outline_reads_reject_unknown_fields_indices_and_unbounded_projection(selector, fields):
    value, document, _ = adapter()
    with pytest.raises(BridgeError): value.read_entities(document, [selector], fields)
