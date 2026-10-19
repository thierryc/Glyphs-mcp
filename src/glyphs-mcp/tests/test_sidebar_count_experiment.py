"""Experimental lifecycle, exact targeting and isolated supervisor regressions."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from sidebar_count_experiment import CountGuard, RestorationError, VARIANTS, classify, interface_batch, validate_child_environment
from run_sidebar_count_experiment import alert_recorded, supervise
from qualify_sidebar_counts_native import workload_source, verify


class Item:
    def __init__(self, font, original=False, predicate="category == 'Letter'"):
        self.font, self.predicate, self.original = font, predicate, original
        self.current, self.writes = original, []
        self.fail = None

    def isSuppressingCount(self):
        return self.current

    def setSuppressCount_(self, flag):
        self.writes.append(flag)
        if self.fail == flag:
            raise RuntimeError("injected setter failure")
        self.current = flag


def test_count_guard_preflights_all_owners_and_accessors():
    font = object(); good = Item(font)
    for bad in (Item(object()), NS(font=font, predicate="valid", isSuppressingCount=False)):
        with pytest.raises(ValueError):
            CountGuard([good, bad], font)
        assert not good.writes


@pytest.mark.parametrize("failure", [None, "script failure", "cancelled between callbacks", "verification failure"])
def test_count_guard_exact_restoration_in_all_exit_paths(failure):
    font = object(); items = [Item(font), Item(font, True), Item(font)]
    selected = Item(font); container = Item(object(), predicate=None)
    guard = CountGuard(items+[selected, container, items[0]], font, [selected])
    guard.start()
    try:
        assert all(item.current for item in items)
        if failure:
            raise RuntimeError(failure)
    except RuntimeError:
        pass
    finally:
        guard.restore()
    assert [item.current for item in items] == [False, True, False]
    assert not selected.writes and not container.writes
    assert all(item.writes == [True, item.original] for item in items)


def test_guard_restores_partial_entry_and_attempts_all_cleanup():
    font = object(); items = [Item(font), Item(font), Item(font)]
    items[1].fail = True
    guard = CountGuard(items, font)
    with pytest.raises(RuntimeError, match="setter failure"):
        guard.start()
    assert all(not item.current for item in items)
    items[1].fail = None
    guard.start(); items[1].fail = False
    with pytest.raises(RestorationError) as error:
        guard.restore()
    assert not items[0].current and not items[2].current
    assert items[1].current and error.value.errors == guard.errors
    assert guard.errors[0]["index"] == 1


def test_guard_rejects_a_silent_setter_and_empty_coverage():
    font = object(); item = Item(font)
    item.setSuppressCount_ = lambda _: None
    with pytest.raises(RuntimeError, match="did not take effect"):
        CountGuard([item], font).start()
    with pytest.raises(ValueError, match="No unselected"):
        CountGuard([item], font, [item])


class Font:
    def __init__(self, enabled=True):
        self.enabled, self.calls = enabled, []
    def isUpdateInterfaceEnabled(self): return self.enabled
    def disableUpdateInterface(self): self.calls.append("disable"); self.enabled = False
    def enableUpdateInterface(self): self.calls.append("enable"); self.enabled = True


@pytest.mark.parametrize("original", [True, False])
@pytest.mark.parametrize("batch", [True, False])
def test_interface_batch_restores_after_error_and_respects_outer_owner(original, batch):
    font = Font(original)
    with pytest.raises(RuntimeError, match="script error"):
        with interface_batch(font, batch):
            assert font.enabled == (original and not batch)
            raise RuntimeError("script error")
    assert font.enabled == original
    assert font.calls == (["disable", "enable"] if original and batch else [])


def matrix():
    return [dict(variant=name, repeat=i, outcome="passed") for name in VARIANTS for i in range(1, 6)]


def test_classification_requires_full_matrix_and_baseline_reproduction():
    runs = matrix()
    assert classify(runs, 5) == "not reproduced"
    assert classify(runs[:-1], 5) == "failed or blocked"
    assert classify(runs+[runs[0]], 5) == "failed or blocked"
    runs[0]["outcome"] = "alert"
    assert classify(runs, 5) == "promising mitigation"
    for row in runs:
        if row["variant"] in {"combined", "suppression-only"}: row["outcome"] = "alert"
    assert classify(runs, 5) == "failed or blocked"
    runs = matrix(); runs[-1]["outcome"] = "alert"
    assert classify(runs, 5) == "failed or blocked"
    runs = matrix(); runs[0]["outcome"] = "timeout"
    assert classify(runs, 5) == "failed or blocked"


def width_example():
    path = ROOT / "skills/glyphs-mcp-scripting/examples/explicit_widths.py"
    spec = importlib.util.spec_from_file_location("explicit_widths", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.apply_widths


def width_font():
    font = Font()
    font.glyphs = {"a": NS(layers=[NS(layerId="M1", width=500), NS(layerId="M2", width=600)]),
                   "b": NS(layers=[NS(layerId="M1", width=700)]), "missing": None}
    return font


def row(name="a", mid="M1", old=500, new=501.25):
    return dict(glyph=name, layer=mid, expectedWidth=old, width=new)


@pytest.mark.parametrize("bad", [row("missing"), row(mid="missing"), row(old=499), row(new=float("nan"))])
def test_explicit_example_preflights_all_before_any_write(bad):
    font = width_font()
    with pytest.raises(ValueError): width_example()(font, [row(), bad])
    assert font.glyphs["a"].layers[0].width == 500 and not font.calls


def test_example_ignores_changed_ui_selection_and_preserves_controls():
    font = width_font()
    # Selection is intentionally misleading; only the supplied row owns the edit.
    font.selectedLayers = [font.glyphs["b"].layers[0]]
    width_example()(font, [row()])
    assert font.glyphs["a"].layers[0].width == 501.25
    assert font.glyphs["a"].layers[1].width == 600
    assert font.glyphs["b"].layers[0].width == 700
    assert font.calls == ["disable", "enable"]


def test_example_restores_interface_after_native_verification_failure():
    class RoundingLayer:
        layerId = "M1"
        width = property(lambda self: 500, lambda self, value: None)
    font = width_font(); font.glyphs["a"].layers = [RoundingLayer()]
    with pytest.raises(RuntimeError, match="differs"):
        width_example()(font, [row()])
    assert font.enabled and font.calls == ["disable", "enable"]


def test_workloads_compile_and_do_not_consult_ui():
    for kind in ("colors", "shapes", "addition"):
        source = workload_source(kind)
        compile(source, kind, "exec")
        assert all(token not in source for token in ("selectedLayers", "font.selection", "predicate", "sidebar."))
        assert source.index("owners.append") < source.index("with interface_batch")


def test_supervisor_ignores_partial_event_records(tmp_path):
    path = tmp_path / "events.jsonl"
    assert not alert_recorded(path)
    path.write_text('{"event":"heartbeat"}\n{"event":"alert"')
    assert not alert_recorded(path)
    path.write_text('{"event":"alert"}\n')
    assert alert_recorded(path)


def test_external_watchdog_terminates_only_its_spawned_process(tmp_path):
    # A stand-in CLI accepts the same argv but only sleeps. No Glyphs is launched.
    cli = tmp_path / "fake-cli"
    cli.write_text("#!/bin/sh\nexec sleep 30\n"); cli.chmod(0o755)
    result = supervise(str(cli), "unused", tmp_path / "run", "baseline", 1, .2)
    assert result["outcome"] == "timeout" and result["exitCode"] != 0
    assert json.loads((tmp_path / "run/supervisor.json").read_text())["outcome"] == "timeout"


def test_full_editor_error_stream_can_import_native_harness(tmp_path, monkeypatch):
    import faulthandler
    import io
    import os
    import qualify_sidebar_counts_native as native

    # Exercise the real import boundary with the editor's descriptor-less
    # stderr, stopping before any fixture creation or native UI access.
    (tmp_path / "native_script_harness.py").write_text(
        "import faulthandler\nfaulthandler.dump_traceback_later(45)\nclass Harness: pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "native_script_harness", raising=False)
    for name, fields in {
        "objc": {},
        "AppKit": dict.fromkeys(("NSApplication", "NSDocumentController", "NSWindowDidBecomeKeyNotification")),
        "Foundation": dict.fromkeys(("NSNotificationCenter", "NSRunLoop", "NSDate", "NSURL")),
        "GlyphsApp": dict(Glyphs=NS(fonts=[object()]), **dict.fromkeys((
            "GSFont", "GSFontMaster", "GSGlyph", "GSPath", "GSNode", "GSComponent"))),
    }.items():
        monkeypatch.setitem(sys.modules, name, NS(**fields))
    observations = []
    monkeypatch.setattr(faulthandler, "dump_traceback_later",
                        lambda _: observations.append(os.fstat(sys.stderr.fileno()).st_mode))
    monkeypatch.setattr(faulthandler, "cancel_dump_traceback_later", lambda: observations.append("cancelled"))
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    output = tmp_path / "result.json"
    monkeypatch.setattr(sys, "argv", ["probe", "--output", str(output), "--variant", "baseline"])
    monkeypatch.setenv("GLYPHS_MCP_SIDEBAR_REPORT_DIR", str(tmp_path))
    monkeypatch.setenv("GLYPHS_MCP_SIDEBAR_PARENT_PGID", str(os.getpgrp()+1))
    try:
        native.main()
        assert len(observations) == 2 and observations[-1] == "cancelled"
        assert "unexpectedly contains existing fonts" in json.loads(output.read_text())["error"]
        assert (tmp_path / "native-python.stderr.log").exists()
    finally:
        sys.modules.pop("native_script_harness", None)


@pytest.mark.parametrize("stop", ["success", "failure", "cancel", "missing"])
def test_guard_surrounds_real_bridge_lifecycle_and_restores_flags(tmp_path, monkeypatch, stop):
    from test_simple_v2_script_capacity import executable_fixture
    source = 'def run(layer, params, context):\n    layer.visits += 1'
    if stop == "failure": source += '\n    raise ValueError("injected native callback failure")'
    core, queue, state, font, request = executable_fixture(tmp_path, monkeypatch, 20, source=source)
    core.chunk_limit = 1  # Make the cancellation boundary deterministic.
    font.selectedLayers = [object()]  # UI selection is not the reviewed scope.
    if stop == "missing": del font.glyphs["g19"]
    item = Item(font); guard = CountGuard([item], font)
    guard.start()
    try:
        core.begin_script(request)
        if stop == "cancel":
            while not core.operation(request["jobId"])["scriptResult"]["executedTargets"]:
                queue.pop(0)()
            core.discard(request["jobId"])
        while queue: queue.pop(0)()
        result = core.operation(request["jobId"])
        assert result["status"] == {"success":"applied", "failure":"failed", "cancel":"cancelled", "missing":"failed"}[stop]
        visits = sum(g.owner.background.visits for g in font.glyphs.values())
        assert visits == {"success":20, "failure":1, "cancel":1, "missing":0}[stop]
        assert result["scriptResult"]["executed"] == (stop != "missing")
    finally:
        guard.restore()
    assert not item.current and item.writes == [True, False]


def test_supervisor_detects_alert_and_never_dismisses_it(tmp_path):
    cli = tmp_path / "fake-alert-cli"
    cli.write_text('#!/usr/bin/env python3\nimport pathlib, sys, time\n'
        'p=pathlib.Path(sys.argv[sys.argv.index("--output")+1])\n'
        '(p.parent/"events.jsonl").write_text(\'{"event":"alert"}\\n\')\n'
        'time.sleep(30)\n')
    cli.chmod(0o755)
    result = supervise(str(cli), "unused", tmp_path / "alert-run", "baseline", 1, 5)
    assert result["outcome"] == "alert" and result["exitCode"] != 0


def test_native_child_refuses_unsupervised_or_same_group_execution(tmp_path):
    path = tmp_path / "result.json"
    for env in ({}, {"GLYPHS_MCP_SIDEBAR_REPORT_DIR":str(tmp_path), "GLYPHS_MCP_SIDEBAR_PARENT_PGID":"10"},
                {"GLYPHS_MCP_SIDEBAR_REPORT_DIR":"/wrong", "GLYPHS_MCP_SIDEBAR_PARENT_PGID":"20"}):
        with pytest.raises(RuntimeError, match="isolated process group"):
            validate_child_environment(path, env, 10)
    validate_child_environment(path, {"GLYPHS_MCP_SIDEBAR_REPORT_DIR":str(tmp_path),
                                     "GLYPHS_MCP_SIDEBAR_PARENT_PGID":"20"}, 10)


def test_generated_workloads_preflight_missing_owners_before_writes(monkeypatch):
    monkeypatch.setitem(sys.modules, "GlyphsApp", NS(GSGlyph=object, GSPath=object, GSNode=object, GSComponent=object))
    first = NS(layers=[NS(layerId="M", shapes=["original"], width=500)], color=3)
    font = Font(); font.masters = [NS(id="M")]; font.glyphs = {"a":first, "missing":None}
    for kind in ("colors", "shapes", "addition"):
        with pytest.raises(AssertionError, match="missing"):
            exec(workload_source(kind), dict(font=font, params=dict(names=["a","missing"], masters=["M"], base="a", batching=True, additions=["new"])))
        assert first.color == 3 and first.layers[0].shapes == ["original"] and not font.calls


@pytest.mark.parametrize('fail', [False, True])
def test_editor_dispatcher_yields_to_native_ui_and_restores_after_workflow(fail):
    from queue import Queue
    from threading import Event, get_ident
    import time
    from qualify_sidebar_counts_native import editor_workflow_steps
    main_thread = get_ident()
    calls = []
    native_completions = []
    flag_item = Item(object())
    guard = CountGuard([flag_item], flag_item.font)
    harness = NS(queue=Queue(), service=NS(close=lambda: calls.append('closed')),
                 temp=NS(cleanup=lambda: calls.append('cleaned')))
    def on_main(callback):
        finished = Event(); result = {}
        def dispatch():
            assert get_ident() == main_thread
            result['value'] = callback()
            finished.set()
        harness.queue.put(dispatch)
        assert finished.wait(2)
        return result.get('value')
    harness.main = on_main
    def exercise(h):
        assert get_ident() != main_thread
        h.main(guard.start)
        try:
            # Simulate the sidebar's main-queue completion. It only becomes
            # available after the current callback returns to the real UI loop.
            h.main(lambda: native_completions.append(lambda: calls.append('native-model-ready')))
            h.main(lambda: calls.index('native-model-ready'))
            if fail: raise RuntimeError('injected workflow failure')
            return {'targetsVerified': True}
        finally:
            h.main(guard.restore)
    steps = editor_workflow_steps(harness, exercise)
    deadline = time.monotonic()+3
    while time.monotonic()<deadline:
        try: next(steps)
        except StopIteration as stopped:
            result = stopped.value
            break
        while native_completions: native_completions.pop(0)()
        time.sleep(.001)
    else: pytest.fail('Editor dispatcher did not finish')
    assert result.get('passed',False) == (not fail)
    if fail: assert 'injected workflow failure' in result['error']
    assert not flag_item.current and flag_item.writes == [True, False]
    assert calls == ['native-model-ready','closed','cleaned']
