"""Typed outline-edit preparation, application and reported-y regression."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
for part in ("protocol", "bridge", "sidecar"):
    sys.path.insert(0, str(ROOT / "src" / part))

from glyphs_mcp_bridge.core import BridgeCore  # noqa: E402
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter  # noqa: E402
from glyphs_mcp_protocol import ProtocolError, validate_outline_options, validate_patch  # noqa: E402
from glyphs_mcp_protocol.outline import path_hash  # noqa: E402
from glyphs_mcp_sidecar import outline_job  # noqa: E402
from glyphs_mcp_sidecar.jobs import JobStore  # noqa: E402
from glyphs_mcp_sidecar.service import ServiceError, SidecarService  # noqa: E402


class Collection(list):
    def __getitem__(self, key):
        if isinstance(key, str):
            for item in self:
                if str(getattr(item, "id", getattr(item, "layerId", ""))) == key:
                    return item
            raise KeyError(key)
        return super().__getitem__(key)


class Nodes(Collection):
    pass


class Node:
    def __init__(self, x, y, kind="line"):
        self.position = (x, y); self.type = kind; self.smooth = False; self.name = None
        self.userData = {"survives": True}
    @property
    def position(self): return self._position
    @position.setter
    def position(self, value): self._position = NS(x=float(value[0]), y=float(value[1]))


class PathShape:
    locked = False
    def __init__(self, nodes, closed=False): self.nodes = Nodes(nodes); self.closed = closed; self.userData = {"path": 1}
    def insertNodeWithPathTime_(self, path_time):
        end, local = int(path_time), path_time-int(path_time)
        before, after = self.nodes[end-1], self.nodes[end]
        x = before.position.x+(after.position.x-before.position.x)*local
        y = before.position.y+(after.position.y-before.position.y)*local
        self.nodes.insert(end, Node(x, y, "line"))
    def reverse(self): self.nodes = Nodes(reversed(self.nodes))
    def makeNodeFirst_(self, previous):
        start = self.nodes.index(previous)+1
        self.nodes = Nodes(self.nodes[start:]+self.nodes[:start])
    def removeNodeCheckKeepShape_(self, target):
        if target not in self.nodes:
            return False
        index = self.nodes.index(target)
        removed = {index}
        if index and self.nodes[index-1].type == "offcurve":
            removed.add(index-1)
        if index+1 < len(self.nodes) and self.nodes[index+1].type == "offcurve":
            removed.add(index+1)
        if index-2 >= 0 and self.nodes[index-2].type == "offcurve":
            node = self.nodes[index-2]
            node.position = (node.position.x-7.5, node.position.y-11.25)
        if index+2 < len(self.nodes) and self.nodes[index+2].type == "offcurve":
            node = self.nodes[index+2]
            node.position = (node.position.x+9.5, node.position.y+3.25)
        self.nodes = Nodes(node for position, node in enumerate(self.nodes) if position not in removed)
        return True


class CubicPathShape(PathShape):
    @staticmethod
    def _lerp(left, right, value):
        return (left.position.x+(right.position.x-left.position.x)*value,
                left.position.y+(right.position.y-left.position.y)*value)

    def insertNodeWithPathTime_(self, path_time):
        end, local = int(path_time), path_time-int(path_time)
        if end != 28 or [self.nodes[index].type for index in range(25, 29)] != ["curve", "offcurve", "offcurve", "curve"]:
            return super().insertNodeWithPathTime_(path_time)
        start, first, second, finish = self.nodes[25:29]
        a = self._lerp(start, first, local)
        b = self._lerp(first, second, local)
        c = self._lerp(second, finish, local)
        b_node = Node(*b, "offcurve")
        first.position = a
        second.position = c
        d = self._lerp(first, b_node, local)
        e = self._lerp(b_node, second, local)
        d_node = Node(*d, "offcurve")
        e_node = Node(*e, "offcurve")
        inserted = Node(d[0]+(e[0]-d[0])*local, d[1]+(e[1]-d[1])*local, "curve")
        self.nodes[27:27] = [d_node, inserted, e_node]


class Layer:
    associatedMasterId = None
    def __init__(self, identity, offset=0):
        self.layerId = self.id = identity; self.isMasterLayer = True; self.isSpecialLayer = False
        self.paths = Collection([PathShape([Node(0+offset, 0), Node(20+offset, 0), Node(40+offset, 0),
                                            Node(95.061+offset, 970), Node(579.061+offset, 1)])])
        self.shapes = list(self.paths); self.components = []; self.anchors = []; self.hints = []
        self.temporarilyDisableRounding = False; self.events = []
    def copy(self): return deepcopy(self)
    def compareString(self): return ";".join("".join(str(node.type) for node in path.nodes) for path in self.paths)
    def setTemporarilyDisableRounding_(self, value): self.temporarilyDisableRounding = bool(value)
    def beginChanges(self): self.events.append("begin")
    def endChanges(self): self.events.append("end")
    def setNeedUpdateShapes(self): self.events.append("refresh")


def fixture():
    masters = Collection([NS(id=f"M{index}", name=f"Master {index}") for index in range(9)])
    layers = Collection([Layer(master.id, index*10) for index, master in enumerate(masters)])
    glyph = NS(name="y", id="glyph-y", layers=layers)
    glyphs = {"y": glyph}
    document = NS(isDocumentEdited=lambda: False, changeCount=lambda: 0, undoManager=lambda: None)
    font = NS(glyphs=glyphs, masters=masters, filepath="/tmp/Nine.glyphs", familyName="Nine", parent=document,
              currentTab=None)
    return font, layers


def request(layer):
    guard = path_hash(outline_job._path_state(layer.paths[0]))
    return {"kind": "outline_edit", "glyphs": [], "options": {
        "compatibilityPolicy": "preserve", "targets": [{"glyph": "y",
        "layers": {"scope": "all_masters"}, "referenceLayer": "M0",
        "guards": [{"path": 0, "hash": guard}], "operations": [{"op": "split_segment",
        "path": 0, "startNode": 3, "endNode": 4, "fractions": [.10, .25, .82],
        "measure": "arc_length"}]}]}}


def native_removal_fixture():
    fractions = [.12761742620054406, .21144546448909946, .27595317896352534,
                 .10571692305434983, .09269473978013612, .21962524467188374]
    masters = Collection([NS(id=f"R{index}", name=f"Removal {index}") for index in range(6)])
    layers = Collection()
    for index, master in enumerate(masters):
        offset = index*12
        nodes = [Node(position*10+offset, position % 3, "line") for position in range(23)]
        nodes.extend([Node(-20+offset, -290, "offcurve"), Node(30+offset, -360, "offcurve"),
                      Node(160+offset, -420, "curve"), Node(180+offset, -425, "offcurve"),
                      Node(230+offset, -430, "offcurve"), Node(320+offset, -390, "curve")])
        layer = Layer(master.id)
        layer.paths = Collection([CubicPathShape(nodes)])
        layer.shapes = list(layer.paths)
        layers.append(layer)
    glyph = NS(name="y", id="glyph-y", layers=layers)
    document = NS(isDocumentEdited=lambda: False, changeCount=lambda: 0, undoManager=lambda: None)
    font = NS(glyphs={"y": glyph}, masters=masters, filepath="/tmp/Six.glyphs",
              familyName="Six", parent=document, currentTab=None)
    targets = []
    for layer, fraction in zip(layers, fractions):
        targets.append({"glyph": "y", "layers": {"scope": "ids", "ids": [layer.id]},
                        "referenceLayer": layer.id,
                        "guards": [{"path": 0, "hash": path_hash(outline_job._path_state(layer.paths[0]))}],
                        "operations": [
                            {"op": "split_segment", "path": 0, "startNode": 25, "endNode": 28,
                             "fractions": [fraction], "measure": "path_time"},
                            {"op": "remove_node", "path": 0, "node": 25},
                        ]})
    return font, layers, {"kind": "outline_edit", "glyphs": [], "options": {
        "compatibilityPolicy": "preserve", "targets": targets}}


def test_reported_y_split_is_prepared_for_all_nine_masters_and_exact_coordinates():
    font, layers = fixture()
    changes, report = outline_job.prepare(font, request(layers[0]))
    assert len(changes) == len(report["layers"]) == 9
    assert all(change["operations"][0]["pathTimes"] == [.10, .25, .82] for change in changes)
    inserted = changes[0]["operations"][0]["inserted"]
    for actual, expected in zip([(node["x"], node["y"]) for node in inserted],
                                [(143.461, 873.1), (216.061, 727.75), (491.941, 175.42)]):
        assert actual == pytest.approx(expected)
    assert all(row["rawNodeDelta"] == 3 for row in report["layers"])
    assert all(len(layer.paths[0].nodes) == 5 for layer in layers), "preparation must use detached copies"


def test_native_remove_node_regression_resolves_removed_and_adjusted_nodes_for_six_masters(monkeypatch):
    monkeypatch.setattr("glyphs_mcp_bridge.core.outline_edit.native_remove_available", lambda: True)
    font, layers, removal = native_removal_fixture()
    changes, report = outline_job.prepare(font, removal)
    assert len(changes) == len(report["layers"]) == 6
    assert all(change["operations"][1] == {
        "op": "remove_node", "path": 0, "node": 25, "removedNodes": [24, 25, 26]
    } for change in changes)
    assert all(row["rawNodeDelta"] == 0 for row in report["layers"])
    assert all(row["nativeRemovals"][0]["removedNodes"] == [24, 25, 26]
               for row in report["layers"])
    assert all([item["index"] for item in row["nativeRemovals"][0]["adjustedNodes"]] == [23, 27]
               for row in report["layers"])
    assert not report["warnings"]
    assert all(len(layer.paths[0].nodes) == 29 for layer in layers), "preparation must stay detached"

    adapter = GlyphsAdapter(NS(fonts=[font])); document = adapter.list_documents()[0]
    patch = validate_patch({"version": 1, "jobId": "native-remove", "documentId": document["id"],
        "sourcePath": document["path"], "sourceHash": "sha256:"+"b"*64,
        "generation": document["generation"], "changes": changes,
        "summary": "Native removal for 6 layers"})
    before = [[id(node) for node in layer.paths[0].nodes] for layer in layers]
    queue = []; core = BridgeCore(adapter, queue.append); core.begin_apply(patch)
    while queue: queue.pop(0)()
    assert core.operation("native-remove")["status"] == "applied"
    for layer, identities in zip(layers, before):
        assert len(layer.paths[0].nodes) == 29
        assert identities[24] not in [id(node) for node in layer.paths[0].nodes]
        assert identities[25] not in [id(node) for node in layer.paths[0].nodes]
        assert identities[26] not in [id(node) for node in layer.paths[0].nodes]
    core.discard("native-remove")
    while queue: queue.pop(0)()
    assert [[id(node) for node in layer.paths[0].nodes] for layer in layers] == before


def test_raw_delete_remains_available_and_reports_curve_geometry_risk():
    font, _, raw = native_removal_fixture()
    for target in raw["options"]["targets"]:
        target["operations"][1] = {"op": "delete_nodes", "path": 0, "nodes": [24, 25, 26]}
    changes, report = outline_job.prepare(font, raw)
    assert all(change["operations"][1]["op"] == "delete_nodes" for change in changes)
    assert all(row["rawDeletionCount"] == 1 and not row["nativeRemovals"] for row in report["layers"])
    assert any("may change contour geometry" in warning for warning in report["warnings"])


def test_remove_node_contract_is_closed_and_resolved_nodes_include_target():
    _, layers = fixture()
    options = request(layers[0])["options"]
    options["targets"][0]["operations"] = [{"op": "remove_node", "path": 0, "node": 3}]
    assert validate_outline_options(options)["targets"][0]["operations"][0] == {
        "op": "remove_node", "path": 0, "node": 3
    }
    options["targets"][0]["operations"][0]["removedNodes"] = [3]
    with pytest.raises(ProtocolError, match="unexpected fields"):
        validate_outline_options(options)

    font, _, removal = native_removal_fixture()
    changes, _ = outline_job.prepare(font, removal)
    bad = deepcopy(changes[0]); bad["operations"][1]["removedNodes"] = [24, 26]
    with pytest.raises(ProtocolError, match="include the requested node"):
        validate_patch({"version": 1, "jobId": "bad-remove", "documentId": "doc",
            "sourcePath": "/tmp/test.glyphs", "sourceHash": "sha256:"+"c"*64,
            "generation": 0, "changes": [bad], "summary": "bad"})


def test_native_remove_rejects_offcurve_no_effect_missing_selector_and_hints():
    _, layers, _ = native_removal_fixture(); layer = layers[0]
    with pytest.raises(Exception, match="on-curve"):
        outline_job._apply(layer.copy(), {"op": "remove_node", "path": 0, "node": 24})

    no_effect = layer.copy(); no_effect.paths[0].removeNodeCheckKeepShape_ = lambda _node: True
    with pytest.raises(Exception, match="did not perform"):
        outline_job._apply(no_effect, {"op": "remove_node", "path": 0, "node": 25})

    unsupported = layer.copy(); unsupported.paths[0].removeNodeCheckKeepShape_ = None
    with pytest.raises(Exception, match="does not support"):
        outline_job._apply(unsupported, {"op": "remove_node", "path": 0, "node": 25})

    hinted = layer.copy(); referenced = hinted.paths[0].nodes[24]
    hinted.hints = [NS(originNode=referenced, targetNode=None, otherNode1=None, otherNode2=None)]
    with pytest.raises(Exception, match="hint reference"):
        outline_job._apply(hinted, {"op": "remove_node", "path": 0, "node": 25})


def test_remove_node_job_requires_its_negotiated_bridge_capability(tmp_path):
    _, layers = fixture(); options = request(layers[0])["options"]
    options["targets"][0]["operations"] = [{"op": "remove_node", "path": 0, "node": 3}]
    document = {"id": "doc", "path": "/tmp/test.glyphs", "dirty": False, "generation": 0}
    bridge = NS(status=lambda: {"writeCapabilities": ["outline.edit.v1"]},
                documents=lambda: [document])
    service = SidecarService(bridge, jobs=JobStore(tmp_path),
                             worker=NS(status=lambda: {"available": True}))
    with pytest.raises(ServiceError, match="outline.remove-node.v1"):
        service.start_job("doc", kind="outline_edit", options=options)


def test_bridge_advertises_native_remove_only_when_selector_is_available(monkeypatch):
    core = BridgeCore(NS(), lambda _callback: None)
    monkeypatch.setattr("glyphs_mcp_bridge.core.outline_edit.native_remove_available", lambda: False)
    assert core.status()["writeCapabilities"] == ["outline.edit.v1"]
    monkeypatch.setattr("glyphs_mcp_bridge.core.outline_edit.native_remove_available", lambda: True)
    assert core.status()["writeCapabilities"] == ["outline.edit.v1", "outline.remove-node.v1"]


def test_prepared_outline_patch_applies_rolls_back_and_discards_without_replacing_survivors():
    font, layers = fixture(); changes, _ = outline_job.prepare(font, request(layers[0]))
    for layer in layers: layer.selection = [layer.paths[0].nodes[3]]
    adapter = GlyphsAdapter(NS(fonts=[font])); document = adapter.list_documents()[0]
    patch = validate_patch({"version": 1, "jobId": "outline-y", "documentId": document["id"],
        "sourcePath": document["path"], "sourceHash": "sha256:"+"a"*64,
        "generation": document["generation"], "changes": changes, "summary": "Outline edits for 9 layers"})
    identities = [[id(node) for node in layer.paths[0].nodes] for layer in layers]
    queue = []; core = BridgeCore(adapter, queue.append); core.begin_apply(patch)
    while queue: queue.pop(0)()
    assert core.operation("outline-y")["status"] == "applied"
    assert all(len(layer.paths[0].nodes) == 8 for layer in layers)
    assert all([id(node) for node in layer.paths[0].nodes if id(node) in before] == before
               for layer, before in zip(layers, identities))
    assert all(layer.selection == [layer.paths[0].nodes[3]] for layer in layers)
    core.discard("outline-y")
    while queue: queue.pop(0)()
    assert core.operation("outline-y")["status"] == "discarded"
    assert [[id(node) for node in layer.paths[0].nodes] for layer in layers] == identities
    assert all(layer.paths[0].userData == {"path": 1} for layer in layers)
    assert all(layer.selection == [layer.paths[0].nodes[3]] for layer in layers)


@pytest.mark.parametrize("mutation", ["unknown", "duplicate", "nan", "too_many"])
def test_outline_options_are_closed_finite_unique_and_bounded(mutation):
    _, layers = fixture(); options = request(layers[0])["options"]
    operation = options["targets"][0]["operations"][0]
    if mutation == "unknown": operation["script"] = "arbitrary Python"
    elif mutation == "duplicate": operation["fractions"] = [.1, .1]
    elif mutation == "nan": operation["fractions"] = [float("nan")]
    else: operation["fractions"] = [index/34 for index in range(1, 34)]
    with pytest.raises(ProtocolError): validate_outline_options(options)


def test_path_guard_and_default_compatibility_policy_reject_stale_or_one_master_topology():
    font, layers = fixture(); stale = request(layers[0]); stale["options"]["targets"][0]["guards"][0]["hash"] = "sha256:"+"0"*64
    with pytest.raises(Exception, match="guard is stale"): outline_job.prepare(font, stale)
    explicit = request(layers[0]); target = explicit["options"]["targets"][0]
    target["layers"] = {"scope": "ids", "ids": ["M0"]}
    with pytest.raises(Exception, match="compatibility"): outline_job.prepare(font, explicit)
    explicit["options"]["compatibilityPolicy"] = "allow_incompatible"
    changes, report = outline_job.prepare(font, explicit)
    assert len(changes) == 1 and report["warning"]


def test_ordered_node_reverse_start_open_and_delete_operations_use_evolving_indices():
    _, layers = fixture(); layer = layers[0]; path = layer.paths[0]; path.closed = True
    original = path.nodes[0]
    operations = [
        {"op": "update_nodes", "path": 0, "updates": [{"index": 0, "delta": {"dx": .5, "dy": -.25},
                                                           "smooth": True, "name": "moved"}]},
        {"op": "reverse_path", "path": 0},
        {"op": "set_start_node", "path": 0, "node": 2},
        {"op": "set_closed", "path": 0, "closed": False, "startNode": 0},
        {"op": "delete_nodes", "path": 0, "nodes": [1]},
    ]
    for operation in operations: outline_job._apply(layer, operation)
    assert not path.closed and len(path.nodes) == 4
    assert original.position.x == pytest.approx(.5) and original.position.y == pytest.approx(-.25)
    assert original.smooth and original.name == "moved"


def test_hint_references_block_destructive_node_and_path_operations():
    _, layers = fixture(); layer = layers[0]; referenced = layer.paths[0].nodes[1]
    layer.hints = [NS(originNode=referenced, targetNode=None, otherNode1=None, otherNode2=None)]
    with pytest.raises(Exception, match="hint reference"):
        outline_job._apply(layer.copy(), {"op": "delete_nodes", "path": 0, "nodes": [1]})
    with pytest.raises(Exception, match="hint reference"):
        outline_job._apply(layer.copy(), {"op": "delete_path", "path": 0})


def test_cubic_and_quadratic_arc_length_mapping_and_degenerate_rejection():
    cubic = [[0, 0], [0, 100], [100, 100], [100, 0]]
    times = outline_job._path_times("curve", cubic, [.25, .5, .75], "arc_length")
    assert times[1] == pytest.approx(.5, abs=1e-5) and times == sorted(times)
    quadratic = [[0, 0], [50, 100], [100, 0]]
    qtimes = outline_job._path_times("qcurve", quadratic, [.5], "arc_length")
    assert qtimes == pytest.approx([.5], abs=1e-5)
    assert outline_job._path_times("curve", cubic, [.2], "path_time") == [.2]
    with pytest.raises(Exception, match="degenerate"):
        outline_job._path_times("line", [[1, 1], [1, 1]], [.5], "arc_length")
