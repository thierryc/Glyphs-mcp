"""Real Reporter callbacks with a virtual main loop and a separately run worker."""

import ast
from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from types import SimpleNamespace

import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src/companions/sdk"))
from glyphs_mcp_companions import visible_layer, invalidate_view, wake_reporter


@pytest.fixture
def reporter():
    source = Path(__file__).resolve().parents[3] / "src/companions/reference-inspector/glyphs_reference_inspector/plugin.py"
    tree = ast.parse(source.read_text())
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Assign))]
    timers, workers, captures, reads, redraws, paints, labels = [], [], [], [], [], [], []
    clock = SimpleNamespace(now=0.0, buttons=0)
    callbacks = {}
    graphics = SimpleNamespace(depth=0)
    def save(): graphics.depth += 1
    def restore(): graphics.depth -= 1
    context = SimpleNamespace(saveGraphicsState=save, restoreGraphicsState=restore)
    layer = SimpleNamespace(parent=SimpleNamespace(name="a"), layerId="regular", master=None,
                            isMasterLayer=True, completeBezierPath=[[0, [[0, 0]]], [1, [[100, 100]]]],
                            completeOpenBezierPath=None, width=510.25, anchors=[])
    host = SimpleNamespace(activeReporters=[], defaults={}, font=SimpleNamespace(
        filepath="/tmp/Disposable.glyphs", currentTab=SimpleNamespace(activeLayer=layer)),
        redraw=lambda: (_ for _ in ()).throw(AssertionError("Global redraw loses native drawing")),
        removeCallback=lambda *_: None, addCallback=lambda cb,event: callbacks.setdefault(event,cb))
    view = SimpleNamespace(setNeedsDisplay_=lambda flag: redraws.append(flag))
    host.font.currentTab.graphicView = lambda: view

    def later(delay, callback, *args):
        timers.append((clock.now + delay, lambda: callback(*args)))

    def advance(seconds=0):
        end = clock.now + seconds
        count = 0
        while timers and min(t[0] for t in timers) <= end:
            count += 1
            assert count < 1000, "Main loop must not spin"
            timers.sort(key=lambda t: t[0])
            due, callback = timers.pop(0)
            clock.now = due
            callback()
        clock.now = end

    class Worker:
        def __init__(self, *, target, **_): self.target = target
        def start(self): workers.append(self.target)

    class Reader:
        error = None

        def __init__(self, *_): pass

        def read(self, request):
            reads.append(request)
            if self.error:
                raise ValueError(self.error)
            return {"label": "Last Saved", "width": 500}

    def capture(path):
        assert not clock.buttons, "Never capture geometry with a held mouse button"
        if path is not None:
            captures.append(deepcopy(path))
        return deepcopy(path or [])

    env = {"ReporterPlugin": object, "Glyphs": host, "RLock": RLock, "Thread": Worker,
           "json": json, "monotonic": lambda: clock.now,
           "objc": SimpleNamespace(python_method=lambda f: f, typedSelector=lambda _: lambda f: f, pyobjc_id=id),
           "NSEvent": SimpleNamespace(pressedMouseButtons=lambda: clock.buttons),
           "NSBundle": SimpleNamespace(mainBundle=lambda: SimpleNamespace(bundlePath=lambda: "/Applications/Glyphs.app")),
           "NSPoint": lambda x, y: (x, y), "NSColor": SimpleNamespace(secondaryLabelColor=lambda: None),
           "AppHelper": SimpleNamespace(callAfter=lambda f, *args: later(0, f, *args), callLater=later),
           "ReferenceReader": Reader, "path_elements": capture,
           "comparison": lambda ref, live: {"width": [ref["width"], live["width"]], "live": live},
           "drawing": SimpleNamespace(prepare=deepcopy, paint=lambda paths, scale: paints.append(paths)),
           "withdraw": lambda _: None}
    env.update(visible_layer=visible_layer, invalidate_view=invalidate_view, wake_reporter=wake_reporter,
        NSGraphicsContext=context, menus=SimpleNamespace(install_menu=lambda _: None), publish=lambda _: None,
        UPDATEINTERFACE="update", DOCUMENTWASSAVED="saved", DOCUMENTOPENED="opened",
        DOCUMENTACTIVATED="activated", TABDIDOPEN="tab", UPDATEEDITVIEWFRAME="frame")
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(source), "exec"), env)
    plugin = env["GlyphsReferenceInspector"]()
    plugin.settings()
    plugin.getScale = lambda: 1
    plugin.drawTextAtPoint = lambda label, *_args, **_kwargs: labels.append(label)

    def finish():
        while workers:
            workers.pop(0)()
        advance()

    def enable():
        plugin.willActivate()
        host.activeReporters = [plugin]
        advance()
        finish()

    return SimpleNamespace(plugin=plugin, host=host, layer=layer, clock=clock, timers=timers,
                           workers=workers, captures=captures, reads=reads, redraws=redraws, paints=paints, labels=labels,
                           advance=advance, finish=finish, enable=enable, view=view, callbacks=callbacks, graphics=graphics, env=env)


def test_activation_displays_without_touching_the_canvas(reporter):
    r = reporter
    r.enable()
    assert len(r.captures) == len(r.reads) == len(r.redraws) == 1
    assert r.plugin._published["paths"]["live"]["width"] == 510.25
    assert not r.timers


@pytest.mark.parametrize("label", ["Loading reference…", "Last Saved · No changes",
                                   "Last Saved · Width +10", "Reference unavailable: Missing file"])
def test_reference_indication_only_draws_on_the_edited_occurrence(reporter, label):
    r = reporter
    r.enable()
    r.plugin._published["label"] = label
    # The edited letter and its repeated text occurrences share one GSLayer.
    # Glyphs routes their drawing through different optional Reporter hooks.
    r.plugin.foreground(r.layer)
    for hook in ("inactiveLayerForeground", "inactiveLayerBackground", "preview"):
        callback = getattr(r.plugin, hook, None)
        if callback is not None:
            callback(r.layer)
            callback(r.layer)
    assert r.labels == [label]
    assert len(r.paints) == 1
    assert len(r.reads) == len(r.redraws) == 1
    assert not r.timers and not r.workers and r.graphics.depth == 0


def test_other_edited_layer_cannot_draw_a_stale_reference_indication(reporter):
    r = reporter
    r.enable()
    r.plugin.foreground(deepcopy(r.layer))
    assert not r.labels and not r.paints


def test_drag_preserves_overlay_and_coalesces_events_until_release(reporter):
    r = reporter
    r.enable()
    previous = r.plugin._published
    r.clock.buttons = 1
    for index in range(1000):
        r.layer.width = 520 + index / 10
        r.plugin.update_(None)
        r.advance(0.005)
        r.plugin.foreground(r.layer)
        assert r.plugin._published is previous
        assert len(r.timers) == 1
    assert len(r.captures) == len(r.reads) == len(r.redraws) == 1
    assert all(paths is previous["paths"] for paths in r.paints)
    r.clock.buttons = 0
    # Release needs no additional UPDATEINTERFACE event.
    r.advance(0.16)
    r.finish()
    assert len(r.captures) == len(r.reads) == len(r.redraws) == 2
    assert r.plugin._published["paths"]["live"]["width"] == r.layer.width
    assert not r.timers


def test_keyboard_edits_wait_for_a_full_quiet_interval(reporter):
    r = reporter
    r.enable()
    for width in (520, 530, 540):
        r.layer.width = width
        r.plugin.update_(None)
        r.advance(0.1)
        assert len(r.captures) == 1
    r.advance(0.06)
    r.finish()
    assert len(r.captures) == 2
    assert r.plugin._published["paths"]["live"]["width"] == 540


def test_edit_rejects_an_older_worker_result_without_clearing_paths(reporter):
    r = reporter
    r.enable()
    previous = r.plugin._published
    r.layer.width = 520
    r.plugin.update_(None)
    r.advance(0.16)
    r.workers.pop(0)()  # Result is queued on the main loop.
    r.layer.width = 530
    r.plugin.update_(None)
    r.advance()
    assert r.plugin._published is previous
    r.advance(0.16)
    r.finish()
    assert r.plugin._published["paths"]["live"]["width"] == 530


def test_mouse_down_before_publication_defers_result_even_without_update_event(reporter):
    r = reporter
    r.enable()
    previous = r.plugin._published
    r.layer.width = 520
    r.plugin.update_(None)
    r.advance(0.16)
    r.clock.buttons = 1
    r.finish()
    assert r.plugin._published is previous
    r.layer.width = 530
    r.clock.buttons = 0
    r.advance(0.16)
    r.finish()
    assert r.plugin._published["paths"]["live"]["width"] == 530


@pytest.mark.parametrize("change", ["layer", "font", "reference", "save"])
def test_context_switch_clears_old_overlay_and_rejects_pending_result(reporter, change):
    r = reporter
    r.enable()
    r.layer.width = 520
    r.plugin.update_(None)
    r.advance(0.16)
    r.workers.pop(0)()
    if change == "layer":
        r.host.font.currentTab.activeLayer = deepcopy(r.layer)
    elif change == "font":
        r.host.font = deepcopy(r.host.font)
        r.host.font.filepath = "/tmp/Other.glyphs"
    elif change == "reference":
        r.plugin._specs[r.host.font.filepath] = {"kind": "file", "source": "/tmp/Original.glyphs"}
    else:
        r.plugin._epoch += 1
    r.plugin.update_(None)
    assert r.plugin._published["paths"] is None
    r.advance()
    assert r.plugin._published["paths"] is None
    r.finish()
    assert r.plugin._published["paths"] is not None
    assert len(r.redraws) == 2


@pytest.mark.parametrize("change", ["deactivate", "close"])
def test_deactivate_or_close_cancels_pending_refresh_and_result(reporter, change):
    r = reporter
    r.enable()
    r.layer.width = 520
    r.plugin.update_(None)
    r.advance(0.16)
    r.workers.pop(0)()
    r.plugin.update_(None)
    if change == "deactivate":
        r.plugin.willDeactivate()
        r.host.activeReporters = []
    else:
        r.host.font = None
        r.plugin.update_(None)
    r.advance(0.2)
    r.finish()
    assert r.plugin._published is None
    assert not r.timers and not r.workers
    assert len(r.redraws) == 1


def test_unchanged_selection_does_not_recompute_or_leave_idle_timer(reporter):
    r = reporter
    r.enable()
    for _ in range(20):
        r.plugin.update_(None)
    r.advance(0.16)
    assert not r.workers and not r.timers
    assert len(r.reads) == len(r.redraws) == 1


def test_failed_refresh_retains_paths_and_does_not_create_redraw_retry_loop(reporter):
    r = reporter
    r.enable()
    previous_paths = r.plugin._published["paths"]
    r.plugin._reader.error = "Reference is unavailable"
    r.layer.width = 520
    r.view.setNeedsDisplay_ = lambda flag: (r.redraws.append(flag), r.plugin.update_(None))
    r.plugin.update_(None)
    r.advance(0.16)
    r.finish()
    r.advance(0.16)
    r.finish()
    assert r.plugin._published["paths"] is previous_paths
    assert "Reference is unavailable" in r.plugin._published["label"]
    assert len(r.redraws) == 2
    assert not r.timers and not r.workers


def test_unsaved_font_reports_status_without_reading_a_reference(reporter):
    r = reporter
    r.host.font.filepath = None
    r.enable()
    assert "Save this font" in r.plugin._published["label"]
    assert not r.reads and not r.captures


@pytest.mark.parametrize("event", ["opened", "activated", "tab", "frame", "controller"])
def test_restored_activation_waits_for_attached_tab_without_canvas_input(reporter, event):
    r = reporter
    tab = r.host.font.currentTab
    r.host.font.currentTab = None
    r.host.activeReporters = [r.plugin]  # Native preference restore: no willActivate.
    r.plugin.start()
    r.advance()
    assert not r.captures
    tab.activeLayer = None
    tab.selectedLayers = [r.layer]  # Restored tab may still be in text mode.
    r.host.font.currentTab = tab
    if event == "controller":
        r.plugin.setController_(tab)
    else:
        r.callbacks[event](None)
    r.advance(); r.finish()
    assert len(r.captures) == len(r.reads) == len(r.redraws) == 1
    # A restored text selection prepares the cache but is not an edited glyph.
    callback = getattr(r.plugin, "inactiveLayerForeground", None)
    if callback is not None:
        callback(r.layer)
    assert not r.paints and not r.labels
    tab.activeLayer = r.layer
    r.plugin.foreground(r.layer)
    assert len(r.paints) == len(r.labels) == 1 and r.graphics.depth == 0
    assert not r.timers


def test_tab_attachment_events_are_coalesced_and_do_not_poll(reporter):
    r = reporter
    r.host.activeReporters = [r.plugin]
    for _ in range(100): r.plugin.setController_(r.host.font.currentTab)
    assert len(r.timers) == 1
    r.advance(); r.finish()
    assert len(r.reads) == 1 and not r.timers


def test_native_canvas_is_invalidated_only_after_atomic_publication(reporter):
    r = reporter
    observed = []
    r.view.setNeedsDisplay_ = lambda _: observed.append(r.plugin._published)
    r.enable()
    first = observed[-1]
    r.layer.width += .125
    r.plugin.update_(None); r.advance(.16)
    assert r.plugin._published is first and len(observed) == 1
    r.finish()
    assert len(observed) == 2 and observed[-1]["paths"]["live"]["width"] == r.layer.width


def test_foreground_restores_graphics_state_even_when_paint_fails(reporter):
    r = reporter; r.enable()
    r.env["drawing"].paint = lambda *_: (_ for _ in ()).throw(ValueError("drawing failed"))
    with pytest.raises(ValueError): r.plugin.foreground(r.layer)
    assert r.graphics.depth == 0
