"""Closed native-action protocol, worker, negotiation, and Undo tests."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest


ROOT = Path(__file__).resolve().parents[3]
for part in ("protocol", "bridge", "sidecar"):
    sys.path.insert(0, str(ROOT / "src" / part))

from glyphs_mcp_bridge import native_actions as bridge_actions  # noqa: E402
from glyphs_mcp_bridge.core import BridgeCore, BridgeError  # noqa: E402
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter  # noqa: E402
from glyphs_mcp_protocol import ProtocolError, validate_patch  # noqa: E402
from glyphs_mcp_protocol.native_actions import (  # noqa: E402
    ACTION_SPECS,
    NATIVE_ACTIONS,
    validate_options,
)
from glyphs_mcp_sidecar import native_action_job as worker_actions  # noqa: E402
from glyphs_mcp_sidecar.jobs import JobStore  # noqa: E402
from glyphs_mcp_sidecar.service import ServiceError, SidecarService  # noqa: E402
from glyphs_mcp_sidecar.worker import WorkerError  # noqa: E402


class Collection(list):
    def __getitem__(self, key):
        if isinstance(key, str):
            for item in self:
                if str(getattr(item, "name", getattr(item, "layerId", ""))) == key:
                    return item
            raise KeyError(key)
        return super().__getitem__(key)


class UndoManager:
    def __init__(self):
        self.groups_by_event = True
        self.level = 0
        self.current = []
        self.undo_groups = []
        self.redo_groups = []
        self.mode = "normal"
        self.enabled = True

    def groupingLevel(self): return self.level
    def groupsByEvent(self): return self.groups_by_event
    def setGroupsByEvent_(self, value): self.groups_by_event = bool(value)
    def beginUndoGrouping(self): self.level += 1; self.current = []
    def endUndoGrouping(self):
        self.level -= 1
        if self.mode == "normal": self.undo_groups.append(list(self.current)); self.redo_groups.clear()
    def setActionName_(self, _name): pass
    def isUndoRegistrationEnabled(self): return self.enabled
    def disableUndoRegistration(self): self.enabled = False
    def enableUndoRegistration(self): self.enabled = True
    def registerUndoWithTarget_handler_(self, target, handler):
        if not self.enabled: return
        if self.mode == "undo": self._redo.append((target, handler))
        elif self.mode == "redo": self._undo.append((target, handler))
        else: self.current.append((target, handler))
    def undo(self):
        group = self.undo_groups.pop(); self._redo = []; self.mode = "undo"
        try:
            for target, handler in reversed(group): handler(target)
        finally: self.mode = "normal"
        self.redo_groups.append(self._redo)
    def redo(self):
        group = self.redo_groups.pop(); self._undo = []; self.mode = "redo"
        try:
            for target, handler in reversed(group): handler(target)
        finally: self.mode = "normal"
        self.undo_groups.append(self._undo)


class NativeLayer:
    isMasterLayer = True
    isSpecialLayer = False
    associatedMasterId = None

    def __init__(self, identity, width=500, *, manager=None, fail=False):
        self.layerId = self.id = identity
        self.state = {"width": width, "shapes": [{"x": 1.25, "y": 2.5}]}
        self.paths = []; self.components = []; self.anchors = []; self.hints = []
        self.guides = []; self.annotations = []; self.name = identity
        self.width = width; self.vertWidth = None; self.vertOrigin = None
        self.leftMetricsKey = self.rightMetricsKey = self.widthMetricsKey = None
        self.topMetricsKey = self.bottomMetricsKey = None
        self.color = None; self.attributes = {}; self.background = None; self.backgroundImage = None
        self.undoManager = manager
        self.fail = fail

    def propertyListValueFormat_(self, _format): return copy.deepcopy(self.state)
    def propertyListValueFormat_error_(self, _format, _error): return copy.deepcopy(self.state), None
    def copy(self):
        result = NativeLayer(self.layerId, manager=None)
        result.state = copy.deepcopy(self.state); result.width = self.width
        return result
    def getCopyOfContentFromLayer_doSelection_(self, other, _selection):
        self.state = copy.deepcopy(other.state); self.width = other.width
    def beginChanges(self): pass
    def endChanges(self): pass
    def setNeedUpdateShapes(self): pass
    def syncMetrics(self):
        self.state["width"] += 25; self.width = self.state["width"]
        if self.fail: raise RuntimeError("native selector failed")
    def addNodesAtExtremes(self, force, check_selection):
        self.state["extremes"] = [bool(force), bool(check_selection)]


class NativeGlyph:
    def __init__(self, name, layers, manager=None):
        self.name = name; self.layers = Collection(layers); self.undoManager = manager
        self.info = {"name": name, "category": "Letter", "layers": ["excluded"]}
        for name, value in {
            "unicode": None, "unicodes": None, "id": "glyph-" + name, "locked": False,
            "axes": [], "category": "Letter", "subCategory": None, "script": "latin", "case": 1,
            "direction": 0, "productionName": None, "sortName": None, "sortNameKeep": None,
            "export": True, "color": None, "note": None, "leftMetricsKey": None,
            "rightMetricsKey": None, "widthMetricsKey": None, "topMetricsKey": None,
            "bottomMetricsKey": None, "tags": [], "group": None, "groupIdx": 0,
            "storeGroup": False, "userData": {}, "leftKerningGroup": None,
            "rightKerningGroup": None, "topKerningGroup": None, "bottomKerningGroup": None,
            "storeCategory": False, "storeSubCategory": False, "storeScript": False,
            "storeCase": False, "storeDirection": False, "storeProductionName": False,
            "storeSortName": False,
        }.items(): setattr(self, name, value)

    def propertyListValueFormat_(self, _format):
        value = copy.deepcopy(self.info); value["category"] = self.category; return value
    def propertyListValueFormat_error_(self, _format, _error): return self.propertyListValueFormat_(_format), None
    def updateGlyphInfo(self, change_name):
        assert change_name is False; self.category = "Symbol"; self.info["category"] = "Symbol"


class Feature:
    def __init__(self, name, code=""):
        self.name = name; self.code = code; self.id = "feature-" + name
        self.automatic = True; self.canBeAutomated = True; self.disabled = False
    def propertyListValueFormat_(self, _format): return {"id": self.id, "name": self.name, "code": self.code, "automatic": self.automatic, "disabled": self.disabled}
    def propertyListValueFormat_error_(self, _format, _error): return self.propertyListValueFormat_(_format), None
    def copy(self):
        result = Feature(self.name, self.code); result.id = self.id; return result
    def update(self): self.code = "automatic update"


class NativeFont:
    def __init__(self, glyphs, masters, document_manager=None):
        self.glyphs = Collection(glyphs); self.masters = Collection(masters)
        self.featurePrefixes = Collection(); self.classes = Collection(); self.features = Collection([Feature("liga", "old")])
        self.filepath = "/tmp/Native.glyphs"; self.familyName = "Native"; self.currentTab = None; self.grid = 1
        self.parent = NS(isDocumentEdited=lambda: False, changeCount=lambda: 0, undoManager=lambda: document_manager)
    def updateFeatures(self): self.features[0].code = "updated"


def fixture(*, two=False, fail_second=False):
    manager = UndoManager()
    masters = Collection([NS(id="M1", name="Regular"), NS(id="M2", name="Bold")])
    first = NativeLayer("M1", 500, manager=manager)
    second = NativeLayer("M2", 600, manager=manager, fail=fail_second)
    special = NativeLayer("brace-500", 550, manager=manager); special.isMasterLayer = False; special.isSpecialLayer = True
    glyph = NativeGlyph("h", [first, second, special], manager)
    font = NativeFont([glyph], masters, manager)
    if not two: font.masters = Collection([masters[0]])
    return font, first, second, special, manager


def request(action="update_metrics", layers=None, arguments=None):
    options = {"action": action}
    if ACTION_SPECS[action]["scope"] == "layer":
        options["targets"] = [{"glyph": "h", "layers": layers or {"scope": "all_masters"}}]
    elif ACTION_SPECS[action]["scope"] == "glyph":
        options["targets"] = [{"glyph": "h"}]
    elif ACTION_SPECS[action]["scope"] == "feature_block":
        options["targets"] = [{"blockType": "feature", "id": "feature-liga"}]
    if arguments is not None: options["arguments"] = arguments
    return {"kind": "native_action", "glyphs": [], "options": options}


def patch(changes, job="native-1"):
    return validate_patch({
        "version": 1, "jobId": job, "documentId": "doc", "sourcePath": "/tmp/Native.glyphs",
        "sourceHash": "sha256:" + "a" * 64, "generation": 0,
        "changes": changes, "summary": "Native action",
    })


def test_registry_is_closed_complete_and_describes_every_runtime_concern():
    assert len(NATIVE_ACTIONS) == 17
    assert set(NATIVE_ACTIONS) == set(ACTION_SPECS)
    for spec in ACTION_SPECS.values():
        assert set(spec) == {"scope", "selectors", "arguments", "callArguments", "projection", "reportFields", "target"}
        assert spec["selectors"] and spec["projection"] and spec["reportFields"] and spec["target"]


@pytest.mark.parametrize("action", NATIVE_ACTIONS)
def test_every_action_has_one_valid_closed_option_shape(action):
    normalized = validate_options(request(action)["options"])
    assert normalized["action"] == action
    assert normalized["scope"] == ACTION_SPECS[action]["scope"]
    assert normalized["arguments"] == ({"force": False} if action == "add_extremes" else {})


@pytest.mark.parametrize("field", ["selector", "menu", "python", "method", "delta", "glyphs"])
def test_native_options_reject_open_ended_or_top_level_job_fields(field):
    options = request()["options"]
    if field in {"delta", "glyphs"}:
        with pytest.raises(ServiceError):
            SidecarService._job_request(
                "native_action", 1 if field == "delta" else None,
                ["h"] if field == "glyphs" else None, options,
            )
    else:
        options[field] = "arbitrary"
        with pytest.raises(ProtocolError, match="unexpected fields"):
            validate_options(options)


def test_layer_scope_arguments_duplicates_and_bounds_are_strict():
    assert validate_options(request("add_extremes", arguments={"force": True})["options"])["arguments"] == {"force": True}
    with pytest.raises(ProtocolError, match="boolean"):
        validate_options(request("add_extremes", arguments={"force": 1})["options"])
    options = request()["options"]
    options["targets"] *= 101
    with pytest.raises(ProtocolError, match="1-100"):
        validate_options(options)
    options = request(layers={"scope": "ids", "ids": ["M1", "M1"]})["options"]
    with pytest.raises(ProtocolError, match="unique"):
        validate_options(options)
    options = request(layers={"scope": "ids", "ids": [str(index) for index in range(4097)]})["options"]
    with pytest.raises(ProtocolError, match="4,096"):
        validate_options(options)
    options = request()["options"]
    options["targets"].append(copy.deepcopy(options["targets"][0]))
    with pytest.raises(ProtocolError, match="unique"):
        validate_options(options)
    with pytest.raises(ProtocolError, match="does not accept targets"):
        validate_options({"action": "update_features", "targets": [{"glyph": "h"}]})
    with pytest.raises(ProtocolError) as caught:
        validate_options({"action": "not_in_the_catalog"})
    assert caught.value.code == "unsupported_action"


def test_native_patch_hashes_are_closed_and_one_action_only():
    before = "sha256:" + "1" * 64; after = "sha256:" + "2" * 64
    change = {"kind": "native_action", "action": "update_metrics", "scope": "layer", "arguments": {},
              "glyph": "h", "layer": "M1", "beforeHash": before, "afterHash": after}
    assert patch([change])["changes"] == [change]
    bad = dict(change, selector="syncMetrics")
    with pytest.raises(ProtocolError): patch([bad])
    other = dict(change, action="round_coordinates", layer="M2")
    with pytest.raises(ProtocolError, match="exactly one action"): patch([change, other])


def test_worker_expands_only_master_layers_but_explicit_ids_allow_special_layers():
    font, first, _second, special, _ = fixture()
    changes, report = worker_actions.prepare(font, request())
    assert [change["layer"] for change in changes] == ["M1"]
    assert first.width == 525 and special.width == 550
    assert report["changedCount"] == 1 and report["noChangeCount"] == 0
    changes, _ = worker_actions.prepare(font, request(layers={"scope": "ids", "ids": ["brace-500"]}))
    assert changes[0]["layer"] == "brace-500" and special.width == 575


def test_worker_reports_noop_and_uses_deterministic_worker_bridge_hashes():
    font, layer, *_ = fixture()
    layer.syncMetrics = lambda: None
    changes, report = worker_actions.prepare(font, request())
    assert changes == []
    assert report["targetCount"] == report["noChangeCount"] == 1
    assert report["targets"][0]["status"] == "no_change"

    font, layer, *_ = fixture()
    before = worker_actions.persistent_state(layer, "layer")
    assert worker_actions.state_hash(before) == bridge_actions.current_hash(layer, "layer")


def test_automatic_feature_block_action_uses_exact_id_and_rejects_manual_source():
    font, *_ = fixture()
    changes, report = worker_actions.prepare(font, request("update_automatic_feature_block"))
    assert changes == [{
        "kind": "native_action", "action": "update_automatic_feature_block",
        "scope": "feature_block", "arguments": {}, "blockType": "feature",
        "id": "feature-liga", "beforeHash": changes[0]["beforeHash"],
        "afterHash": changes[0]["afterHash"],
    }]
    assert report["targets"][0]["target"] == {
        "scope": "feature_block", "blockType": "feature", "id": "feature-liga"
    }
    font.features[0].automatic = False
    with pytest.raises(WorkerError, match="automatic"):
        worker_actions.prepare(font, request("update_automatic_feature_block"))


def test_worker_enforces_target_and_job_state_bounds_before_publication(monkeypatch):
    font, layer, *_ = fixture()
    layer.state["payload"] = "x" * 200
    monkeypatch.setattr(worker_actions, "MAX_TARGET_STATE_BYTES", 32)
    with pytest.raises(WorkerError, match="8 MiB"):
        worker_actions.prepare(font, request())

    font, *_ = fixture(two=True)
    monkeypatch.setattr(worker_actions, "MAX_TARGET_STATE_BYTES", 8 * 1024 * 1024)
    monkeypatch.setattr(worker_actions, "MAX_JOB_STATE_BYTES", 1)
    with pytest.raises(WorkerError, match="64 MiB"):
        worker_actions.prepare(font, request())


def test_fixed_native_arguments_match_worker_and_bridge_dispatch():
    calls = []
    owner = NS(addNodesAtExtremes=lambda *args: calls.append(args))
    worker_actions.invoke(owner, "add_extremes", {"force": True})
    bridge_actions.invoke(owner, "add_extremes", {"force": False})
    assert calls == [(True, False), (False, False)]
    calls = []
    owner = NS(removeOverlap=lambda *args: calls.append(args), updateGlyphInfo=lambda *args: calls.append(args))
    worker_actions.invoke(owner, "remove_overlap", {})
    bridge_actions.invoke(owner, "update_glyph_info", {})
    assert calls == [(False,), (False,)]


def test_sidecar_filters_unknown_actions_and_gates_job_kind(tmp_path):
    document = {"id": "doc", "path": "/tmp/Native.glyphs", "dirty": False, "generation": 0}
    bridge = NS(
        status=lambda: {"writeCapabilities": ["native.action.v1"],
                        "nativeActions": ["unknown", "update_metrics", "add_extremes"]},
        documents=lambda: [document],
    )
    service = SidecarService(bridge, jobs=JobStore(tmp_path), worker=NS(status=lambda: {"available": True}))
    status = service.get_status()
    assert status["nativeActions"] == ["add_extremes", "update_metrics"]
    assert "native_action" in status["jobKinds"] and "native.action.v1" in status["writeCapabilities"]
    bridge.status = lambda: {"writeCapabilities": [], "nativeActions": ["update_metrics"]}
    status = service.get_status()
    assert status["nativeActions"] == [] and "native_action" not in status["jobKinds"]
    with pytest.raises(ServiceError, match="not advertised"):
        service.start_job("doc", kind="native_action", options=request()["options"])


def test_bridge_apply_native_undo_redo_and_discard_are_exact(monkeypatch):
    monkeypatch.setattr("glyphs_mcp_bridge.core.native_actions.available_actions", lambda: ["update_metrics"])
    worker_font, *_ = fixture()
    changes, _ = worker_actions.prepare(worker_font, request())
    live_font, layer, _second, _special, manager = fixture()
    adapter = GlyphsAdapter(NS(fonts=[live_font])); document = adapter.list_documents()[0]
    value = validate_patch({**patch(changes), "documentId": document["id"]})
    queue = []; core = BridgeCore(adapter, queue.append)
    core.begin_apply(value)
    while queue: queue.pop(0)()
    assert core.operation("native-1")["status"] == "applied" and layer.width == 525
    manager.undo(); assert layer.width == 500
    manager.redo(); assert layer.width == 525
    core.discard("native-1")
    while queue: queue.pop(0)()
    assert core.operation("native-1")["status"] == "discarded" and layer.width == 500


def test_bridge_status_advertises_native_action_only_with_a_qualified_action(monkeypatch):
    core = BridgeCore(NS(), lambda _callback: None)
    monkeypatch.setattr("glyphs_mcp_bridge.core.native_actions.available_actions", lambda: [])
    assert "native.action.v1" not in core.status()["writeCapabilities"]
    assert core.status()["nativeActions"] == []
    monkeypatch.setattr("glyphs_mcp_bridge.core.native_actions.available_actions", lambda: ["update_metrics"])
    assert "native.action.v1" in core.status()["writeCapabilities"]
    assert core.status()["nativeActions"] == ["update_metrics"]


def test_native_action_acceptance_revalidates_hash_and_releases_snapshots(monkeypatch):
    monkeypatch.setattr("glyphs_mcp_bridge.core.native_actions.available_actions", lambda: ["update_metrics"])
    worker_font, *_ = fixture()
    changes, _ = worker_actions.prepare(worker_font, request())
    live_font, layer, *_ = fixture()
    adapter = GlyphsAdapter(NS(fonts=[live_font])); document = adapter.list_documents()[0]
    adapter.save_document = lambda *_args: {"nativeSaveSucceeded": True}
    value = validate_patch({**patch(changes, job="native-accept"), "documentId": document["id"]})
    queue = []; core = BridgeCore(adapter, queue.append)
    core.begin_apply(value)
    while queue: queue.pop(0)()
    assert layer.width == 525
    core.begin_accept("native-accept", {
        "saveId": "native-accept", "documentId": document["id"], "saveMode": "save",
        "previousPath": document["path"], "path": document["path"],
    })
    while queue: queue.pop(0)()
    assert core.operation("native-accept")["status"] == "saved"
    completed = core.complete_accept("native-accept", verified=True, receipt={"verified": True})
    assert completed["status"] == "accepted"
    assert core._operations["native-accept"]["resolved"] == []
    assert core._operations["native-accept"]["nativeStateBytes"] == 0


def test_bridge_rolls_back_a_mid_batch_native_failure(monkeypatch):
    monkeypatch.setattr("glyphs_mcp_bridge.core.native_actions.available_actions", lambda: ["update_metrics"])
    worker_font, *_ = fixture(two=True)
    changes, _ = worker_actions.prepare(worker_font, request())
    live_font, first, second, _special, _manager = fixture(two=True, fail_second=True)
    adapter = GlyphsAdapter(NS(fonts=[live_font])); document = adapter.list_documents()[0]
    value = validate_patch({**patch(changes, job="native-fail"), "documentId": document["id"]})
    queue = []; core = BridgeCore(adapter, queue.append, chunk_limit=1)
    core.begin_apply(value)
    while queue: queue.pop(0)()
    result = core.operation("native-fail")
    assert result["status"] == "failed" and result["error"]["code"] == "native_write_failed"
    assert first.width == 500 and second.width == 600


def test_bridge_restores_the_current_target_on_native_readback_mismatch(monkeypatch):
    monkeypatch.setattr("glyphs_mcp_bridge.core.native_actions.available_actions", lambda: ["update_metrics"])
    worker_font, *_ = fixture()
    changes, _ = worker_actions.prepare(worker_font, request())
    live_font, layer, *_ = fixture()
    def wrong_metrics():
        layer.state["width"] += 10; layer.width = layer.state["width"]
    layer.syncMetrics = wrong_metrics
    adapter = GlyphsAdapter(NS(fonts=[live_font])); document = adapter.list_documents()[0]
    value = validate_patch({**patch(changes, job="native-readback"), "documentId": document["id"]})
    queue = []; core = BridgeCore(adapter, queue.append)
    core.begin_apply(value)
    while queue: queue.pop(0)()
    result = core.operation("native-readback")
    assert result["status"] == "failed" and result["error"]["code"] == "readback_failed"
    assert result["error"]["details"]["recovery"]["currentTargetRestored"] is True
    assert layer.width == 500


def test_bridge_rejects_native_patch_missing_live_capability(monkeypatch):
    monkeypatch.setattr("glyphs_mcp_bridge.core.native_actions.available_actions", lambda: [])
    value = patch([{"kind": "native_action", "action": "update_metrics", "scope": "layer", "arguments": {},
                   "glyph": "h", "layer": "M1", "beforeHash": "sha256:" + "1" * 64,
                   "afterHash": "sha256:" + "2" * 64}])
    with pytest.raises(BridgeError) as caught:
        BridgeCore(NS(), lambda _callback: None).begin_apply(value)
    assert caught.value.code == "unsupported_change"
