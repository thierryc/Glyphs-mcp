"""Qualify background outline reads/edits in an isolated, plugin-free Glyphs process.

Run: glyphs run --app '/Applications/Glyphs 4.app' --plugins '' SCRIPT
Uses disposable source files; never connects to the user's open documents.
"""

import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from qualify_simple_v2_outline_edit_native import (  # noqa: E402
    GSLayer, GSPath, GSNode, GSGlyph, LINE, NSPoint, NSUndoManager,
    GlyphsAdapter, BridgeCore, native_worker, outline_job, outline_edit,
    path_hash, patch_for, snapshot, drain, save,
)
from glyphs_mcp_bridge.core import BridgeError  # noqa: E402


def main():
    font = native_worker._load_font(ROOT / "src/glyphs-mcp/tests/fixtures/headless-preview-minimal.glyphs")
    glyph = GSGlyph("backgroundProbe"); font.glyphs.append(glyph)
    mid = str(font.masters[0].id)
    layer = GSLayer(); layer.layerId = mid; layer.associatedMasterId = mid
    glyph.layers[mid] = layer
    path = GSPath(); path.closed = True
    for point in ((100, 0), (100, 700), (200, 700), (200, 100), (500, 100), (500, 0)):
        path.nodes.append(GSNode(NSPoint(*point), LINE))
    layer.shapes.append(path); layer.width = 650
    with tempfile.TemporaryDirectory(prefix="glyphs-background-native-") as directory:
        wrapper = NS(glyphs=font.glyphs, masters=font.masters, filepath=str(Path(directory) / "Probe.glyphspackage"),
                     familyName="Background Probe", currentTab=None,
                     parent=NS(isDocumentEdited=lambda: False, changeCount=lambda: 0, undoManager=lambda: None))
        adapter = GlyphsAdapter(NS(fonts=[wrapper])); document = adapter.list_documents()[0]
        selector = {"kind": "paths", "glyph": glyph.name, "layer": mid, "surface": "background"}
        assert not layer.hasBackground()
        try:
            adapter.read_entities(document["id"], [selector], ["items"])
            raise AssertionError("missing background was not rejected")
        except BridgeError as error:
            assert error.code == "target_not_found"
        assert not layer.hasBackground(), "read created a background"
        layer.background = layer.copy()
        background = layer.background
        foreground_before, background_before = snapshot(layer), snapshot(background)
        paths = adapter.read_entities(document["id"], [selector], ["items"])[0]["values"]
        assert paths["items"][0]["pathHash"] == path_hash(outline_job._path_state(background.paths[0]))
        bounds = adapter.read_entities(document["id"], [{"kind": "layer", "glyph": glyph.name,
            "id": mid, "surface": "background"}], ["id", "bounds"])[0]["values"]
        assert bounds["id"] == mid and bounds["bounds"]["width"] == 400
        # Scale all contours by 75.125%, then center them in the 650-unit advance.
        updates = [{"index": i, "position": {"x": (node.position.x - 100) * .75125 + 174.75,
                                               "y": node.position.y * .75125 + .375}}
                   for i, node in enumerate(background.paths[0].nodes)]
        request = {"kind": "outline_edit", "options": {"targets": [{"glyph": glyph.name,
            "surface": "background", "referenceLayer": mid, "layers": {"scope": "ids", "ids": [mid]},
            "guards": [{"path": 0, "hash": paths["items"][0]["pathHash"]}],
            "operations": [{"op": "update_nodes", "path": 0, "updates": updates}]}]}}
        changes, report = outline_job.prepare(font, request)
        assert snapshot(layer) == foreground_before and snapshot(background) == background_before
        # Use a real NSUndoManager without the headless host's automatic outer group.
        manager = NSUndoManager.alloc().init(); manager.setGroupsByEvent_(False)
        begin = adapter.begin_undo
        class Scope:
            def manager_for(self, owner):
                assert owner == layer, "background edits must use the owning layer's Undo history"
                if manager.groupingLevel() == 0: manager.beginUndoGrouping()
                return manager
            def finish(self, name):
                if manager.groupingLevel():
                    manager.setActionName_(name); manager.endUndoGrouping()
        def begin_undo(document_id):
            begin(document_id); adapter._undo_managers[document_id] = Scope()
        adapter.begin_undo = begin_undo
        queue = []; core = BridgeCore(adapter, queue.append)
        core.begin_apply(patch_for(document, changes, "native-background")); drain(queue)
        assert core.operation("native-background")["status"] == "applied", core.operation("native-background")
        assert outline_edit.hash_layer(background) == changes[0]["afterHash"]
        assert snapshot(layer) == foreground_before
        assert abs(background.bounds.origin.x + background.bounds.size.width / 2 - layer.width / 2) < 1e-8
        manager.undo(); assert snapshot(background) == background_before
        manager.redo(); assert outline_edit.hash_layer(background) == changes[0]["afterHash"]
        save(font, Path(wrapper.filepath))
        reopened = native_worker._load_font(Path(wrapper.filepath))
        assert outline_edit.hash_layer(reopened.glyphs[glyph.name].layers[mid].background) == changes[0]["afterHash"]
        core.discard("native-background"); drain(queue)
        assert core.operation("native-background")["status"] == "discarded", core.operation("native-background")
        assert snapshot(background) == background_before and snapshot(layer) == foreground_before
        broken = [dict(changes[0], afterHash="sha256:" + "0" * 64)]
        queue = []; failed = BridgeCore(adapter, queue.append)
        failed.begin_apply(patch_for(document, broken, "native-background-failure")); drain(queue)
        assert failed.operation("native-background-failure")["status"] == "failed"
        assert failed.operation("native-background-failure")["error"]["details"]["recovery"]["complete"]
        assert snapshot(background) == background_before and snapshot(layer) == foreground_before
    result = {"passed": True, "host": "Glyphs 4.1 (4107)", "isolatedProcess": True,
              "missingBackgroundReadNonmutating": True, "backgroundBoundsAndPaths": True,
              "fractionalScaleAndCenter": True, "foregroundPreserved": True,
              "nativeUndoRedo": True, "discard": True, "partialWriteRecovery": True,
              "saveReopen": True, "reportSurface": report["layers"][0]["surface"]}
    output = ROOT / "build/background-edit-native.json"; output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
