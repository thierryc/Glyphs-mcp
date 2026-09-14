"""Exercise the Reporter lifecycle with controlled host and worker queues."""

import ast
from pathlib import Path
from threading import RLock
from types import SimpleNamespace

import pytest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src/companions/sdk"))
from glyphs_mcp_companions import visible_layer, invalidate_view, wake_reporter


@pytest.fixture
def reporter():
    source = Path(__file__).resolve().parents[3] / "src/companions/curve-inspector/glyphs_curve_inspector/plugin.py"
    tree = ast.parse(source.read_text())
    # Run the actual lifecycle methods without importing Cocoa into pytest.
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
             and node.name in ("_value", "coverage_notice", "GlyphsCurveInspector")]
    main_queue, workers, redraws, captures = [], [], [], []
    callbacks = {}
    graphics = SimpleNamespace(depth=0)
    def save(): graphics.depth += 1
    def restore(): graphics.depth -= 1
    context = SimpleNamespace(saveGraphicsState=save, restoreGraphicsState=restore)
    layer = object()
    host = SimpleNamespace(activeReporters=[], font=SimpleNamespace(
        upm=1000, currentTab=SimpleNamespace(activeLayer=layer)),
        redraw=lambda: (_ for _ in ()).throw(AssertionError("Global redraw loses native drawing")),
        removeCallback=lambda *_: None, addCallback=lambda cb,event: callbacks.setdefault(event,cb))
    view = SimpleNamespace(setNeedsDisplay_=lambda flag: redraws.append(flag))
    host.font.currentTab.graphicView = lambda: view

    class Worker:
        def __init__(self, *, target, **_kwargs):
            self.target = target

        def start(self):
            workers.append(self.target)

    def capture(layer):
        captures.append(layer)
        return [((0, 0), (0, 100), (100, 100), (100, 0))], dict(limitReason=None, omittedComponentCount=0)

    namespace = {"ReporterPlugin": object, "Glyphs": host, "RLock": RLock, "Thread": Worker,
                 "objc": SimpleNamespace(python_method=lambda f: f, typedSelector=lambda _: lambda f: f, pyobjc_id=id),
                 "AppHelper": SimpleNamespace(callAfter=lambda f, *args: main_queue.append(lambda: f(*args))),
                 "extract_visible_cubics": capture,
                 "build_curvature_comb": lambda curves, **_: {"strokes": list(curves)},
                 "MANIFEST": {"id": "curve-inspector"}, "withdraw": lambda _: None}
    namespace.update(visible_layer=visible_layer, invalidate_view=invalidate_view, wake_reporter=wake_reporter,
        NSGraphicsContext=context, menus=SimpleNamespace(install_menu=lambda _: None), publish=lambda _: None,
        UPDATEINTERFACE="update", DOCUMENTWASSAVED="saved", DOCUMENTOPENED="opened",
        DOCUMENTACTIVATED="activated", TABDIDOPEN="tab", UPDATEEDITVIEWFRAME="frame")
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(source), "exec"), namespace)
    instance = namespace["GlyphsCurveInspector"]()
    instance.settings()

    def drain(queue):
        while queue:
            queue.pop(0)()

    def enable():
        instance.willActivate()
        host.activeReporters = [instance]
        drain(main_queue)
        drain(workers)
        drain(main_queue)

    return SimpleNamespace(plugin=instance, host=host, main=main_queue, workers=workers,
                           redraws=redraws, captures=captures, drain=drain, enable=enable, view=view, callbacks=callbacks, graphics=graphics, env=namespace)


def test_activation_paints_without_an_updateinterface_or_canvas_event(reporter):
    r = reporter
    r.plugin.willActivate()
    assert not r.captures and not r.workers  # Host has not activated it yet.
    r.host.activeReporters = [r.plugin]
    r.drain(r.main)
    assert r.captures == [r.host.font.currentTab.activeLayer]
    assert not r.redraws  # Analysis remains outside the host callback.
    r.drain(r.workers)
    r.drain(r.main)
    assert r.redraws == [True]
    assert r.plugin._cache_layer_id == id(r.host.font.currentTab.activeLayer)


def test_reenabling_unchanged_geometry_requests_a_new_display(reporter):
    r = reporter
    r.enable()
    r.plugin.willDeactivate()
    r.host.activeReporters = []
    assert r.plugin._cache_layer_id is None
    r.enable()
    assert r.redraws == [True, True]
    r.plugin.update_(None)
    assert not r.workers  # Ordinary unchanged updates remain coalesced.


def test_deactivation_rejects_an_in_flight_overlay(reporter):
    r = reporter
    r.plugin.willActivate()
    r.host.activeReporters = [r.plugin]
    r.drain(r.main)
    r.drain(r.workers)
    assert r.main  # The worker result is waiting to publish.
    r.plugin.willDeactivate()
    r.host.activeReporters = []
    r.drain(r.main)
    assert not r.redraws
    assert r.plugin._cache_layer_id is None


def test_identical_geometry_on_a_new_layer_still_redraws(reporter):
    r = reporter
    r.enable()
    r.host.font.currentTab.activeLayer = object()
    r.plugin.update_(None)
    r.drain(r.workers)
    r.drain(r.main)
    assert r.redraws == [True, True]
    assert r.plugin._cache_layer_id == id(r.host.font.currentTab.activeLayer)


@pytest.mark.parametrize("event", ["opened", "activated", "tab", "frame", "controller"])
def test_restored_curve_reporter_initializes_without_toggle_or_canvas_input(reporter, event):
    r = reporter; tab = r.host.font.currentTab; layer = tab.activeLayer
    r.host.font.currentTab = None; r.host.activeReporters = [r.plugin]
    r.plugin.start(); r.drain(r.main); r.drain(r.workers); r.drain(r.main)
    r.redraws.clear(); r.captures.clear()
    tab.activeLayer = None; tab.selectedLayers = [layer]; r.host.font.currentTab = tab
    if event == "controller": r.plugin.setController_(tab)
    else: r.callbacks[event](None)
    r.drain(r.main); r.drain(r.workers); r.drain(r.main)
    assert r.captures == [layer] and r.redraws == [True]
    assert r.plugin._cache_layer_id == id(layer)


def test_curve_cache_stays_visible_while_changed_geometry_is_analyzed(reporter):
    r = reporter; r.enable(); layer = r.host.font.currentTab.activeLayer
    previous = r.plugin._cache
    r.env['extract_visible_cubics'] = lambda _: ([((0, 0), (5, 100), (100, 100), (100, 0))], dict(limitReason=None, omittedComponentCount=0))
    r.plugin.update_(None)
    assert r.plugin._cache_layer_id == id(layer) and r.plugin._cache is previous
    assert len(r.redraws) == 1
    r.drain(r.workers); r.drain(r.main)
    assert r.plugin._cache is not previous and len(r.redraws) == 2


def test_curve_graphics_scope_balances_on_early_return(reporter):
    r = reporter
    r.plugin.foreground(object())
    assert r.graphics.depth == 0


def test_component_only_change_refreshes_notice_without_changed_cubics(reporter):
    r = reporter; r.enable()
    curves = r.plugin._cache['strokes']
    r.env['extract_visible_cubics'] = lambda _: (curves, dict(limitReason=None, omittedComponentCount=1))
    r.plugin.update_(None); r.drain(r.workers); r.drain(r.main)
    assert '1 component omitted' in r.plugin._cache['notice']
    r.env['extract_visible_cubics'] = lambda _: (curves, dict(limitReason=None, omittedComponentCount=0))
    r.plugin.update_(None); r.drain(r.workers); r.drain(r.main)
    assert r.plugin._cache['notice'] == ''
    assert len(r.redraws) == 3


def test_coverage_change_during_worker_rejects_stale_result(reporter):
    r = reporter; r.enable()
    curves = r.plugin._cache['strokes']
    r.env['extract_visible_cubics'] = lambda _: (curves, dict(limitReason=None, omittedComponentCount=1))
    r.plugin.update_(None); r.drain(r.workers)
    r.env['extract_visible_cubics'] = lambda _: (curves, dict(limitReason=None, omittedComponentCount=2))
    r.plugin.update_(None)
    r.drain(r.main)
    assert r.plugin._cache['notice'] == ''
    r.drain(r.workers); r.drain(r.main)
    assert '2 components omitted' in r.plugin._cache['notice']


def test_no_notice_for_deactivated_or_other_layer(reporter):
    r = reporter; r.enable()
    r.plugin._cache['notice'] = 'partial'
    r.host.font.currentTab.activeLayer = object()
    r.plugin.foregroundInViewCoords()  # Must return before text/viewport access.
    r.plugin.willDeactivate()
    r.plugin.foregroundInViewCoords()
    assert r.graphics.depth == 0
