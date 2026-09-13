"""First-launch help is application-wide, event-driven and persistent."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def welcome():
    observers, pending, windows = [], [], []
    class Center:
        def addObserverForName_object_queue_usingBlock_(self, name, owner, queue, callback):
            item = (name, callback); observers.append(item); return item
        def removeObserver_(self, item): observers.remove(item)
    class Window:
        visible = False
        shows = 0
        def makeKeyAndOrderFront_(self, sender): self.visible = True; self.shows += 1
        def isVisible(self): return self.visible
        def close(self): self.visible = False
    app = NS(active=False, modal=None)
    from collections import defaultdict
    defaults = defaultdict(lambda: None)
    env = {'objc': NS(python_method=lambda f: f), 'GeneralPlugin': object,
           'Glyphs': NS(defaults=defaults), 'WELCOME_KEY': 'welcome',
           'AppHelper': NS(callAfter=lambda f: pending.append(f)),
           'AK': NS(NSApp=NS(isActive=lambda: app.active, modalWindow=lambda: app.modal),
                    NSApplicationDidFinishLaunchingNotification='launch',
                    NSApplicationDidBecomeActiveNotification='active', NSWindowDidBecomeKeyNotification='key'),
           'NSNotificationCenter': NS(defaultCenter=lambda: Center())}
    tree = ast.parse((ROOT/'src/bridge/glyphs_mcp_bridge/server_panel.py').read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    exec(compile(ast.Module(body=[cls], type_ignores=[]), '<welcome>', 'exec'), env)
    controller = env['GlyphsMCPServerPlugin'](); controller.settings()
    def create(layout):
        window = Window(); windows.append(window); return window
    controller._create_window = create
    return NS(ui=controller, app=app, defaults=defaults, observers=observers, pending=pending, windows=windows)


def test_first_launch_waits_for_active_ui_and_sets_seen_only_after_display(welcome):
    w = welcome
    w.ui._schedule_welcome(); w.pending.pop(0)()
    assert not w.windows and not w.defaults['welcome']
    assert len(w.observers) == 3
    w.app.active = True
    w.observers[0][1](None); w.pending.pop(0)()
    assert w.defaults['welcome'] is True
    assert w.windows[0].visible and not w.observers


def test_modal_defers_until_a_native_window_event_without_polling(welcome):
    w = welcome; w.app.active = True; w.app.modal = object()
    w.ui._schedule_welcome(); w.pending.pop(0)()
    assert not w.defaults['welcome'] and not w.pending
    w.app.modal = None
    w.observers[-1][1](None); w.pending.pop(0)()
    assert len(w.windows) == 1 and w.defaults['welcome']


def test_seen_preference_survives_restart_but_manual_heart_always_works(welcome):
    w = welcome; w.defaults['welcome'] = True; w.app.active = True
    w.ui._schedule_welcome(); w.pending.pop(0)()
    assert not w.windows and not w.observers
    w.ui.showWelcome_(None); w.ui.closeWelcome_(None); w.ui.showWelcome_(None)
    assert len(w.windows) == 1 and w.windows[0].shows == 2


def test_failed_display_does_not_consume_first_launch(welcome):
    w = welcome; w.app.active = True
    def fail(name): raise RuntimeError('native window unavailable')
    w.ui._create_window = fail
    w.ui._schedule_welcome()
    w.pending.pop(0)()
    assert not w.defaults['welcome']
    assert w.observers


def test_heart_has_accessibility_and_does_not_enlarge_palette():
    source = (ROOT/'src/bridge/glyphs_mcp_bridge/plugin.py').read_text()
    assert 'heart.circle' in source
    assert 'Welcome & Support' in source
    assert 'setAccessibilityLabel_' in source
    assert 'PALETTE_HEIGHT = 30' in source


def test_unsuccessful_native_presentation_does_not_mark_seen(welcome):
    w=welcome; w.app.active=True
    w.ui._create_window=lambda layout: NS(makeKeyAndOrderFront_=lambda sender: None, isVisible=lambda: False)
    w.ui._schedule_welcome(); w.pending.pop(0)()
    assert not w.defaults['welcome'] and w.observers


def test_multiple_document_notifications_reuse_one_window(welcome):
    w=welcome; w.app.active=True
    w.ui._schedule_welcome(); w.ui._schedule_welcome()
    assert len(w.pending)==1
    w.pending.pop(0)()
    for _ in range(3): w.ui._schedule_welcome()
    w.pending.pop(0)()
    assert len(w.windows)==1 and w.windows[0].shows==1
    w.ui.showWelcome_(None);w.ui.showWelcome_(None)
    assert len(w.windows)==1 and w.windows[0].shows==3
