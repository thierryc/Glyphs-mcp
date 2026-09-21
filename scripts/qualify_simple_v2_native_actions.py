"""Qualify the closed native-action catalog in the exact Glyphs 4 runtime."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
for part in ("protocol", "bridge", "sidecar"):
    sys.path.insert(0, str(ROOT / "src" / part))

from Foundation import NSPoint, NSUndoManager, NSURL
from GlyphsApp import (
    CORNER, LINE, OFFCURVE, CURVE, GSAnchor, GSComponent, GSFeature, GSFont,
    GSGlyph, GSHint, GSLayer, GSNode, GSPath, GSPackageBundle, Glyphs,
)

from glyphs_mcp_bridge import native_actions as bridge_actions
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter
from glyphs_mcp_bridge.native_undo import write_value
from glyphs_mcp_protocol.native_actions import ACTION_SPECS, NATIVE_ACTIONS
from glyphs_mcp_sidecar import native_action_job as worker_actions, native_worker


FIXTURE = ROOT / "GlyphsSDK/ObjectWrapper/UnitTest/Glyphs Unit Test Sans.glyphs"


def state_hash(owner, scope, change=None):
    worker_owner = bridge_actions._feature_block(owner, change)[2] if scope == "feature_block" else owner
    worker_state = worker_actions.persistent_state(worker_owner, scope)
    bridge_state = bridge_actions.persistent_state(owner, scope, change)
    worker_hash = worker_actions.state_hash(worker_state)
    bridge_hash = bridge_actions.current_hash(owner, scope)
    assert worker_state == bridge_state and worker_hash == bridge_hash
    return worker_hash


def add_open_paths(font):
    glyph = GSGlyph("nativeConnectProbe"); font.glyphs.append(glyph)
    layer = glyph.layers[font.masters[0].id]
    for points in (((0, 0), (100, 0)), ((100, 0), (200, 50))):
        path = GSPath(); path.closed = False
        for point in points: path.nodes.append(GSNode(NSPoint(*point), LINE))
        layer.shapes.append(path)
    return layer


def add_cleanup_path(font):
    glyph = GSGlyph("nativeCleanupProbe"); font.glyphs.append(glyph)
    layer = glyph.layers[font.masters[0].id]
    path = GSPath(); path.closed = True
    for point in ((0, 0), (100, 0), (100, 0), (100, 100), (0, 100)):
        path.nodes.append(GSNode(NSPoint(*point), LINE))
    layer.shapes.append(path)
    return layer


def setup(action):
    font = GSFont(str(FIXTURE))
    arguments = {"force": False} if action == "add_extremes" else {}
    if action == "update_metrics":
        layer = font.glyphs["a"].layers[0]
        layer.rightMetricsKey = "A"; layer.RSB = 1
        return font, layer, arguments
    if action == "correct_path_direction":
        layer = font.glyphs["a"].layers[0]; layer.paths[0].reverse()
        return font, layer, arguments
    if action == "round_coordinates":
        layer = font.glyphs["a"].layers[0]
        node = layer.paths[0].nodes[0]
        layer.setTemporarilyDisableRounding_(True)
        node.position = NSPoint(node.x + 0.4, node.y + 0.2)
        return font, layer, arguments
    if action == "add_extremes": return font, font.glyphs["test_addNodesAtExtremes"].layers[0], arguments
    if action == "cleanup_paths": return font, add_cleanup_path(font), arguments
    if action == "remove_overlap": return font, font.glyphs["a"].layers[1], arguments
    if action == "add_missing_anchors":
        layer = font.glyphs["o"].layers[0]
        while len(layer.anchors): del layer.anchors[0]
        return font, layer, arguments
    if action == "align_components":
        layer = font.glyphs["adieresis"].layers[0]
        component = layer.components[0]; component.automaticAlignment = True
        component.pyobjc_instanceMethods.setPositionFast_(NSPoint(37, 19))
        return font, layer, arguments
    if action == "decompose_components": return font, font.glyphs["adieresis"].layers[0], arguments
    if action == "decompose_corners": return font, font.glyphs["c"].layers[0], arguments
    if action == "make_components":
        layer = font.glyphs["adieresis"].layers[0]; layer.decomposeComponents()
        return font, layer, arguments
    if action == "reinterpolate": return font, font.glyphs["o"].layers[1], arguments
    if action == "connect_open_paths": return font, add_open_paths(font), arguments
    if action == "swap_foreground_background": return font, font.glyphs["a"].layers[0], arguments
    if action == "update_glyph_info":
        glyph = font.glyphs["A"]; glyph.category = "Symbol"; glyph.storeCategory = False
        return font, glyph, arguments
    if action == "update_features":
        feature = next((item for item in font.features if str(item.name) == "liga"), None)
        if feature is None:
            feature = GSFeature(); feature.name = "liga"; font.features.append(feature)
        feature.automatic = True; feature.code = "sub a a by a;"
        return font, font, arguments
    if action == "update_automatic_feature_block":
        feature = next((item for item in font.features if str(item.name) == "liga"), None)
        if feature is None:
            feature = GSFeature(); feature.name = "liga"; font.features.append(feature)
        feature.automatic = True; feature.code = "sub a a by a;"
        assert bridge_actions._value(feature, "canBeAutomated", None) is True
        identity = bridge_actions._value(feature, "identifier", None) or bridge_actions._value(feature, "id", None)
        return font, font, arguments, {"blockType": "feature", "id": str(identity)}
    raise AssertionError(action)


def qualify(action):
    values = setup(action)
    font, owner, arguments = values[:3]
    change = values[3] if len(values) == 4 else None
    scope = ACTION_SPECS[action]["scope"]
    before_hash = state_hash(owner, scope, change)
    action_evidence = {}
    if action == "update_metrics":
        action_evidence = {
            "beforeRSB": float(owner.RSB),
            "metricsKeyRSB": float(font.glyphs["A"].layers[0].RSB),
        }
        assert action_evidence["beforeRSB"] != action_evidence["metricsKeyRSB"]
    if action == "update_glyph_info":
        action_evidence["nameBefore"] = str(owner.name)
    manager = NSUndoManager.alloc().init(); manager.setGroupsByEvent_(False); manager.beginUndoGrouping()
    key = {"kind": "native_action", "action": action, "scope": scope, "arguments": arguments}
    if change is not None: key.update(change)
    write_value(
        manager,
        owner,
        key,
        lambda target: bridge_actions.invoke(target, action, arguments, key),
        lambda target, item: bridge_actions.capture(target, item["scope"], item),
        GlyphsAdapter._write_native_action,
    )
    manager.endUndoGrouping()
    after_hash = state_hash(owner, scope, change)
    changed = before_hash != after_hash
    if action == "update_metrics":
        action_evidence["afterRSB"] = float(owner.RSB)
        assert action_evidence["afterRSB"] == action_evidence["metricsKeyRSB"]
    if action == "update_glyph_info":
        action_evidence["nameAfter"] = str(owner.name)
        assert action_evidence["nameAfter"] == action_evidence["nameBefore"]
    manager.undo(); undo_hash = state_hash(owner, scope, change)
    manager.redo(); redo_hash = state_hash(owner, scope, change)
    assert undo_hash == before_hash and redo_hash == after_hash
    manager.undo(); assert state_hash(owner, scope, change) == before_hash
    selector_owner = bridge_actions._feature_block(owner, change)[2] if change is not None else owner
    return {
        "action": action,
        "scope": scope,
        "selector": next(name for name in ACTION_SPECS[action]["selectors"] if callable(getattr(selector_owner, name, None))),
        "changed": changed,
        "beforeHash": before_hash,
        "afterHash": after_hash,
        "undo": undo_hash == before_hash,
        "redo": redo_hash == after_hash,
        "restored": True,
        "evidence": action_evidence,
    }


def persisted_reload_probe():
    font, layer, arguments = setup("update_metrics")
    bridge_actions.invoke(layer, "update_metrics", arguments)
    expected = state_hash(layer, "layer")
    with tempfile.TemporaryDirectory(prefix="glyphs-native-actions-") as temporary:
        target = Path(temporary) / "Accepted.glyphspackage"
        result = font.saveToURL_type_error_(NSURL.fileURLWithPath_(str(target)), GSPackageBundle, None)
        success = result[0] if isinstance(result, tuple) else result
        assert success
        reopened = native_worker._load_font(target)
        observed = state_hash(reopened.glyphs["a"].layers[0], "layer")
        assert observed == expected
    return {"destination": "temporary .glyphspackage", "expectedHash": expected, "observedHash": observed}


def main():
    advertised = bridge_actions.available_actions()
    assert advertised == sorted(NATIVE_ACTIONS), (advertised, sorted(NATIVE_ACTIONS))
    results = [qualify(action) for action in NATIVE_ACTIONS]
    assert all(item["changed"] for item in results), [item["action"] for item in results if not item["changed"]]
    persisted = persisted_reload_probe()
    print(json.dumps({
        "glyphsVersion": str(Glyphs.versionString),
        "glyphsBuild": str(Glyphs.buildNumber),
        "advertised": advertised,
        "observable": [item["action"] for item in results if item["changed"]],
        "results": results,
        "acceptedReload": persisted,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
