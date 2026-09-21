"""Native nine-master outline-edit qualification in an isolated Glyphs process."""

import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
for part in ("sidecar", "protocol", "bridge"):
    sys.path.insert(0, str(ROOT / "src" / part))

import objc
from Foundation import NSPoint, NSUndoManager, NSURL
from GlyphsApp import (GSGlyph, GSFontMaster, GSLayer, GSPath, GSNode, GSAnchor,
                       GSComponent, GSHint, LINE, CURVE, QCURVE, OFFCURVE, STEM, GSPackageBundle)

from glyphs_mcp_bridge import outline_edit
from glyphs_mcp_bridge.core import BridgeCore
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.native_undo import write_value
from glyphs_mcp_protocol import validate_patch
from glyphs_mcp_protocol.outline import path_hash
from glyphs_mcp_sidecar import native_worker, outline_job


def native_id(value):
    return int(objc.pyobjc_id(value))


def save(font, path):
    result = font.saveToURL_type_error_(NSURL.fileURLWithPath_(str(path)), GSPackageBundle, None)
    success = result[0] if isinstance(result, tuple) else result
    if not success:
        raise RuntimeError("native qualification font could not be saved")


def snapshot(layer):
    path = layer.paths[0]
    return {
        "hash": outline_edit.hash_layer(layer),
        "path": native_id(path),
        "nodes": [(native_id(node), dict(node.userData)) for node in path.nodes],
        "component": [(native_id(item), tuple(item.transform)) for item in layer.components],
        "anchor": [(anchor.name, float(anchor.position.x), float(anchor.position.y)) for anchor in layer.anchors],
        "hints": [(native_id(hint), native_id(hint.originNode), native_id(hint.targetNode)) for hint in layer.hints],
        "shapes": [(type(shape).__name__, native_id(shape)) for shape in layer.shapes],
        "selection": [native_id(item) for item in layer.selection],
    }


def drain(queue):
    calls = 0
    while queue:
        queue.pop(0)(); calls += 1
    return calls


def native_remove_probe(spec, target, *, closed=False):
    path = GSPath(); path.closed = closed
    for point, kind in spec:
        path.nodes.append(GSNode(NSPoint(*point), kind))
    before = list(path.nodes); identities = [native_id(node) for node in before]
    result = path.removeNodeCheckKeepShape_(before[target])
    after = {native_id(node) for node in path.nodes}
    return bool(result), [index for index, identity in enumerate(identities) if identity not in after]


def patch_for(document, changes, job_id):
    return validate_patch({"version": 1, "jobId": job_id, "documentId": document["id"],
        "sourcePath": document["path"], "sourceHash": "sha256:" + "a"*64,
        "generation": document["generation"], "changes": changes,
        "summary": "Native nine-master outline edit"})


def main():
    font = native_worker._load_font(ROOT / "src/glyphs-mcp/tests/fixtures/headless-preview-minimal.glyphs")
    for glyph in list(font.glyphs):
        del font.glyphs[glyph.name]
    while len(font.masters) < 9:
        master = font.masters[0].copy() if font.masters else GSFontMaster()
        master.id = str(uuid4()); master.name = "Outline " + str(len(font.masters) + 1)
        font.masters.append(master)
    masters = list(font.masters)[:9]
    mids = [str(master.id) for master in masters]

    base = GSGlyph("outlineBase"); font.glyphs.append(base)
    subject = GSGlyph("y"); font.glyphs.append(subject)
    for master_index, mid in enumerate(mids):
        base_layer = GSLayer(); base_layer.layerId = mid; base_layer.associatedMasterId = mid
        base.layers[mid] = base_layer
        base_path = GSPath(); base_path.closed = True
        for x, y in ((0, 0), (40, 0), (40, 40), (0, 40)):
            base_path.nodes.append(GSNode(NSPoint(x, y), LINE))
        base_layer.shapes.append(base_path); base_layer.width = 100

        layer = GSLayer(); layer.layerId = mid; layer.associatedMasterId = mid
        subject.layers[mid] = layer
        component = GSComponent("outlineBase"); component.automaticAlignment = False
        component.position = NSPoint(20.125 + master_index, 30.25)
        layer.shapes.append(component)
        path = GSPath(); path.closed = False; path.userData["pathMetadata"] = "keep"
        offset = master_index * 10
        points = ((offset, 0), (20 + offset, 0), (40 + offset, 0),
                  (95.061 + offset, 970), (579.061 + offset, 1))
        for index, (x, y) in enumerate(points):
            node = GSNode(NSPoint(x, y), LINE); node.userData["logicalNode"] = index
            path.nodes.append(node)
        layer.shapes.append(path)
        layer.anchors.append(GSAnchor("top", NSPoint(300.125 + offset, 970)))
        hint = GSHint(); hint.type = STEM; hint.originNode = path.nodes[0]; hint.targetNode = path.nodes[1]
        layer.hints.append(hint); layer.width = 700.125
        layer.selection = [path.nodes[3]]

    removal_subject = GSGlyph("removeNode"); font.glyphs.append(removal_subject)
    removal_fractions = [.12761742620054406, .21144546448909946, .27595317896352534,
                         .10571692305434983, .09269473978013612, .21962524467188374]
    for master_index, mid in enumerate(mids[:6]):
        layer = GSLayer(); layer.layerId = mid; layer.associatedMasterId = mid
        removal_subject.layers[mid] = layer
        path = GSPath(); path.closed = False
        offset = master_index * 12
        for position in range(23):
            path.nodes.append(GSNode(NSPoint(position*10+offset, position % 3), LINE))
        for point, kind in (((-20+offset, -290), OFFCURVE), ((30+offset, -360), OFFCURVE),
                            ((160+offset, -420), CURVE), ((180+offset, -425), OFFCURVE),
                            ((230+offset, -430), OFFCURVE), ((320+offset, -390), CURVE)):
            path.nodes.append(GSNode(NSPoint(*point), kind))
        layer.shapes.append(path)

    root = Path(tempfile.mkdtemp(prefix="glyphs-outline-native-"))
    wrapper = NS(glyphs=font.glyphs, masters=font.masters, filepath=str(root / "Nine.glyphspackage"),
                 familyName="Outline Native", currentTab=None,
                 parent=NS(isDocumentEdited=lambda: False, changeCount=lambda: 0, undoManager=lambda: None))
    adapter = GlyphsAdapter(NS(fonts=[wrapper])); document = adapter.list_documents()[0]
    native_begin = adapter.begin_undo
    class HeadlessScope:
        def manager_for(self, _layer): return None
        def finish(self, _name): return None
    def begin_without_headless_auto_group(document_id):
        native_begin(document_id); adapter._undo_managers[document_id] = HeadlessScope()
    adapter.begin_undo = begin_without_headless_auto_group
    reference = subject.layers[mids[0]]
    request = {"kind": "outline_edit", "glyphs": [], "options": {
        "compatibilityPolicy": "preserve", "targets": [{"glyph": "y",
        "layers": {"scope": "all_masters"}, "referenceLayer": mids[0],
        "guards": [{"path": 0, "hash": path_hash(outline_job._path_state(reference.paths[0]))}],
        "operations": [{"op": "split_segment", "path": 0, "startNode": 3,
        "endNode": 4, "fractions": [.10, .25, .82], "measure": "arc_length"}]}]}}
    changes, report = outline_job.prepare(font, request)
    assert len(changes) == 9 and len(report["layers"]) == 9
    expected = [(143.461, 873.1), (216.061, 727.75), (491.941, 175.42)]
    actual = [(item["x"], item["y"]) for item in changes[0]["operations"][0]["inserted"]]
    assert all(abs(x-a) < .001 and abs(y-b) < .001 for (x, y), (a, b) in zip(actual, expected))
    baseline = {mid: snapshot(subject.layers[mid]) for mid in mids}
    baseline_shapes = {mid: outline_edit.shape_state(subject.layers[mid]) for mid in mids}

    # Preview/application and whole-job discard, with a small chunk size proving yields.
    queue = []; core = BridgeCore(adapter, queue.append, chunk_limit=2)
    core.begin_apply(patch_for(document, changes, "native-outline-apply")); callbacks = drain(queue)
    assert core.operation("native-outline-apply")["status"] == "applied" and callbacks >= 5, core.operation("native-outline-apply")
    for mid in mids:
        layer = subject.layers[mid]; before = baseline[mid]
        assert len(layer.paths[0].nodes) == 8
        assert [(native_id(node), dict(node.userData)) for node in layer.paths[0].nodes if "logicalNode" in node.userData] == before["nodes"]
        assert snapshot(layer)["component"] == before["component"] and snapshot(layer)["anchor"] == before["anchor"]
        assert snapshot(layer)["hints"] == before["hints"] and snapshot(layer)["selection"] == before["selection"]
    core.discard("native-outline-apply"); drain(queue)
    assert core.operation("native-outline-apply")["status"] == "discarded", {
        "operation": core.operation("native-outline-apply"), "before": baseline_shapes[mids[0]],
        "after": outline_edit.shape_state(subject.layers[mids[0]])}
    assert all(snapshot(subject.layers[mid]) == baseline[mid] for mid in mids)

    # Partial failure rollback.
    broken = [dict(change) for change in changes]; broken[4] = dict(broken[4], afterHash="sha256:" + "0"*64)
    queue = []; failed = BridgeCore(adapter, queue.append, chunk_limit=2)
    failed.begin_apply(patch_for(document, broken, "native-outline-failure")); drain(queue)
    assert failed.operation("native-outline-failure")["status"] == "failed"
    assert failed.operation("native-outline-failure")["error"]["details"]["recovery"]["complete"]
    assert all(snapshot(subject.layers[mid]) == baseline[mid] for mid in mids)

    # Cancellation after one native layer write rolls back that write.
    queue = []; cancelled = BridgeCore(adapter, queue.append, chunk_limit=1)
    cancelled.begin_apply(patch_for(document, changes, "native-outline-cancel")); queue.pop(0)()
    cancelled.discard("native-outline-cancel"); drain(queue)
    assert cancelled.operation("native-outline-cancel")["status"] == "cancelled"
    assert all(snapshot(subject.layers[mid]) == baseline[mid] for mid in mids)

    # Real NSUndoManager Undo/Redo on one layer.
    layer, change = subject.layers[mids[0]], changes[0]
    manager = NSUndoManager.alloc().init(); manager.setGroupsByEvent_(False); manager.beginUndoGrouping()
    write_value(manager, layer, change, lambda owner: outline_edit.apply(owner, change),
                outline_edit.capture, GlyphsAdapter._write_exact)
    manager.endUndoGrouping(); after_hash = change["afterHash"]
    assert outline_edit.hash_layer(layer) == after_hash
    manager.undo(); assert snapshot(layer) == baseline[mids[0]]
    manager.redo(); assert outline_edit.hash_layer(layer) == after_hash

    # Save/reopen proves the accepted nine-master topology persists. The live
    # font is then restored so the isolated process finishes at its baseline.
    manager.undo(); assert snapshot(layer) == baseline[mids[0]]
    queue = []; accepted = BridgeCore(adapter, queue.append, chunk_limit=2)
    accepted.begin_apply(patch_for(document, changes, "native-outline-save")); drain(queue)
    assert accepted.operation("native-outline-save")["status"] == "applied"
    save(font, Path(wrapper.filepath)); reopened = native_worker._load_font(Path(wrapper.filepath))
    assert all(len(reopened.glyphs["y"].layers[mid].paths[0].nodes) == 8 for mid in mids)
    accepted.discard("native-outline-save"); drain(queue)
    assert all(snapshot(subject.layers[mid]) == baseline[mid] for mid in mids)

    # The reported keep-shape regression: split a cubic, remove old on-curve
    # 25 through Glyphs' native primitive, and preserve the six-master topology.
    removal_targets = []
    for mid, fraction in zip(mids[:6], removal_fractions):
        layer = removal_subject.layers[mid]
        removal_targets.append({"glyph": "removeNode", "layers": {"scope": "ids", "ids": [mid]},
            "referenceLayer": mid,
            "guards": [{"path": 0, "hash": path_hash(outline_job._path_state(layer.paths[0]))}],
            "operations": [
                {"op": "split_segment", "path": 0, "startNode": 25, "endNode": 28,
                 "fractions": [fraction], "measure": "path_time"},
                {"op": "remove_node", "path": 0, "node": 25},
            ]})
    removal_request = {"kind": "outline_edit", "glyphs": [], "options": {
        "compatibilityPolicy": "preserve", "targets": removal_targets}}
    removal_changes, removal_report = outline_job.prepare(font, removal_request)
    assert len(removal_changes) == len(removal_report["layers"]) == 6
    assert all(change["operations"][1]["removedNodes"] == [24, 25, 26]
               for change in removal_changes)
    assert all([item["index"] for item in row["nativeRemovals"][0]["adjustedNodes"]] == [23, 27]
               for row in removal_report["layers"])
    assert all(row["rawNodeDelta"] == 0 for row in removal_report["layers"])
    removal_baseline = {mid: snapshot(removal_subject.layers[mid]) for mid in mids[:6]}
    queue = []; removal_core = BridgeCore(adapter, queue.append, chunk_limit=2)
    removal_core.begin_apply(patch_for(document, removal_changes, "native-remove-node")); drain(queue)
    assert removal_core.operation("native-remove-node")["status"] == "applied"
    assert all(len(removal_subject.layers[mid].paths[0].nodes) == 29 for mid in mids[:6])
    removal_core.discard("native-remove-node"); drain(queue)
    assert removal_core.operation("native-remove-node")["status"] == "discarded"
    assert all(snapshot(removal_subject.layers[mid]) == removal_baseline[mid] for mid in mids[:6])
    line_probe = native_remove_probe([
        ((0, 0), LINE), ((100, 0), LINE), ((200, 0), LINE)], 1)
    qcurve_probe = native_remove_probe([
        ((0, 0), LINE), ((40, 80), OFFCURVE), ((80, 0), QCURVE),
        ((120, -80), OFFCURVE), ((160, 0), QCURVE)], 2)
    closed_probe = native_remove_probe([
        ((0, 0), CURVE), ((50, -50), OFFCURVE), ((100, -50), OFFCURVE),
        ((150, 0), CURVE), ((180, 50), OFFCURVE), ((130, 120), OFFCURVE),
        ((75, 100), CURVE), ((30, 90), OFFCURVE), ((-30, 50), OFFCURVE)], 0,
        closed=True)
    assert line_probe == (True, [1])
    assert qcurve_probe == (True, [2])
    assert closed_probe == (True, [0, 1, 8])
    result = {"passed": True, "masters": 9, "inserted": actual,
              "preview": True, "apply": True, "partialFailureRollback": True,
              "cancellation": True, "undoRedo": True, "wholeJobDiscard": True,
              "saveReopen": True, "selectionIntegrity": True, "hintIdentity": True,
              "nativeRemoveNode": True, "nativeRemoveLayers": 6,
              "nativeRemoveVariants": ["line", "cubic", "qcurve", "closed-wrap"],
              "componentAnchorPreservation": True, "uiChunkCallbacks": callbacks,
              "boundedRetainedOperations": len(core._operations)}
    output = ROOT / "build/outline-edit-native.json"; output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n"); print(json.dumps(result))


if __name__ == "__main__":
    main()
