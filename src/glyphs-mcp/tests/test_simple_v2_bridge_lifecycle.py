"""App-wide bridge startup and its native Edit-menu action."""

import gc
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from weakref import WeakSet

import pytest


REPO = Path(__file__).resolve().parents[3]
for root in ("src/bridge", "src/protocol", "src/companions/sdk"):
    sys.path.insert(0, str(REPO / root))

from glyphs_mcp_bridge import lifecycle  # noqa: E402


@pytest.fixture
def host(monkeypatch):
    servers, callbacks, registries, refreshed, commands = [], [], [], [], []

    class MenuItem:
        @classmethod
        def new(cls):
            return cls()

        def setTitle_(self, value):
            self.title = value

        def setTarget_(self, value):
            self.target = value

        def setAction_(self, value):
            self.action = value

    class Server:
        fail = False

        def __init__(self, *args, **kwargs):
            if self.fail:
                raise OSError("Address already in use")
            servers.append(self)
            self.alive = False
            self.thread = SimpleNamespace(is_alive=lambda: self.alive)
            self.address = ("127.0.0.1", kwargs["port"])

        def start(self):
            self.alive = True

        def stop(self):
            self.alive = False

    glyphs = SimpleNamespace(
        menu={"edit": []},
        addCallback=lambda callback, event: callbacks.append(callback),
        removeCallback=lambda callback: callbacks.remove(callback),
    )
    runtime = lifecycle.BridgeLifecycle()
    palettes = WeakSet()
    runtime.palettes = SimpleNamespace(addObject_=palettes.add, allObjects=lambda: list(palettes))
    monkeypatch.setattr(lifecycle, "bridge_lifecycle", runtime)
    monkeypatch.setattr(lifecycle, "load_or_create_token", lambda: "test-token")
    monkeypatch.setattr(lifecycle, "CocoaMainThread", lambda: SimpleNamespace(schedule=lambda f: None))
    monkeypatch.setattr(lifecycle, "GlyphsAdapter", lambda glyphs: SimpleNamespace(note_change=lambda _: None))
    monkeypatch.setattr(lifecycle, "BridgeCore", lambda *args: SimpleNamespace(companions=object(), status=lambda: {"activeOperations": 0}))
    monkeypatch.setattr(lifecycle, "BridgeHTTPServer", Server)
    monkeypatch.setattr(lifecycle, "attach_registry", registries.append)
    monkeypatch.setattr(lifecycle, "detach_registry", lambda registry: registries.remove(registry) if registry in registries else None)
    monkeypatch.setitem(sys.modules, "objc", SimpleNamespace(python_method=lambda f: f))
    appkit = SimpleNamespace(NSMenuItem=MenuItem)
    for name in ("NSColor", "NSFont", "NSMakeRect", "NSTextField", "NSView", "NSViewWidthSizable", "NSBackingStoreBuffered", "NSButton", "NSSwitchButton", "NSWindow", "NSWindowStyleMaskClosable", "NSWindowStyleMaskTitled", "NSWorkspace"):
        setattr(appkit, name, object)
    monkeypatch.setitem(sys.modules, "AppKit", appkit)
    monkeypatch.setitem(sys.modules, "Foundation", SimpleNamespace(NSHashTable=object, NSURL=object, NSNotificationCenter=object))
    monkeypatch.setitem(sys.modules, "GlyphsApp", SimpleNamespace(Glyphs=glyphs, EDIT_MENU="edit", UPDATEINTERFACE="update"))
    monkeypatch.setitem(sys.modules, "GlyphsApp.plugins", SimpleNamespace(PalettePlugin=object, GeneralPlugin=object))
    monkeypatch.setitem(sys.modules, "PyObjCTools", SimpleNamespace(AppHelper=object))
    spec = importlib.util.spec_from_file_location("bridge_menu_test_plugin", REPO / "src/bridge/glyphs_mcp_bridge/plugin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.GlyphsMCPBridgePlugin, "_refresh_palette", lambda self: refreshed.append(id(self)))

    panel_spec = importlib.util.spec_from_file_location("glyphs_mcp_bridge.test_server_panel", REPO / "src/bridge/glyphs_mcp_bridge/server_panel.py")
    panel = importlib.util.module_from_spec(panel_spec)
    panel_spec.loader.exec_module(panel)
    def build_window(self):
        self.window = SimpleNamespace(makeKeyAndOrderFront_=lambda _: None)
    monkeypatch.setattr(panel.GlyphsMCPServerPlugin, "_build_window", build_window)
    monkeypatch.setattr(panel.GlyphsMCPServerPlugin, "_run", lambda self, action: commands.append(action))
    control = panel.GlyphsMCPServerPlugin()
    control.settings()
    monkeypatch.setattr(control, "_schedule_welcome", lambda: None)

    def palette():
        value = module.GlyphsMCPBridgePlugin()
        runtime.palettes.addObject_(value)
        return value

    return SimpleNamespace(runtime=runtime, glyphs=glyphs, palette=palette,
                           servers=servers, callbacks=callbacks, registries=registries, control=control, commands=commands,
                           refreshed=refreshed, server_class=Server)


def test_multiple_palettes_and_menu_starts_preserve_one_bridge_and_job_state(host):
    first, second = host.palette(), host.palette()
    host.control.start()
    first.start()
    core = host.runtime.core
    core.pending_job = "keep this reversible operation"
    second.start()
    first.start()
    item = host.glyphs.menu["edit"][0]
    item.action(item)

    assert len(host.glyphs.menu["edit"]) == 1
    assert item.title == "Glyphs MCP Server…"
    assert host.commands == ["status"]
    assert len(host.servers) == len(host.callbacks) == len(host.registries) == 1
    assert host.runtime.core is core
    assert core.pending_job == "keep this reversible operation"
    assert host.runtime.ready
    assert id(first) in host.refreshed and id(second) in host.refreshed


def test_edit_menu_retries_failed_start_and_refreshes_every_palette(host):
    first, second = host.palette(), host.palette()
    host.server_class.fail = True
    host.control.start()
    first.start()
    second.start()
    item = host.glyphs.menu["edit"][0]
    assert host.runtime.startup_error == "Address already in use"
    assert not host.callbacks and not host.registries

    host.server_class.fail = False
    host.refreshed.clear()
    host.runtime.start(host.glyphs, "update")
    assert host.runtime.ready and host.runtime.startup_error is None
    assert len(host.glyphs.menu["edit"]) == len(host.servers) == 1
    assert set(host.refreshed) == {id(first), id(second)}


def test_closing_another_palette_keeps_bridge_and_menu_owner_alive(host):
    first, second = host.palette(), host.palette()
    host.control.start()
    first.start()
    second.start()
    del first, second
    gc.collect()
    assert host.runtime.ready
    assert len(host.runtime.palettes.allObjects()) == 0
    assert host.runtime.menu_target is not None
    assert len(host.callbacks) == 1


def test_menu_is_available_without_any_document_palette(host):
    host.control.start()
    assert not host.runtime.palettes.allObjects()
    item = host.glyphs.menu['edit'][0]
    item.action(item)
    assert host.commands == ['status']
    assert host.runtime.ready


def test_stop_does_not_restart_when_another_document_palette_opens(host):
    host.control.start()
    old_core = host.runtime.core
    host.runtime.stop(host.glyphs)
    assert old_core.paused
    host.palette().start()
    assert host.runtime.stopped and not host.runtime.ready
    assert not host.callbacks and not host.registries
    host.runtime.start(host.glyphs, 'update')
    assert host.runtime.ready and not host.runtime.stopped


def test_stop_waits_for_a_native_write_to_finish(host):
    host.control.start()
    host.runtime.core.status = lambda: {'activeOperations': 1}
    with pytest.raises(RuntimeError, match='current font operation'):
        host.runtime.stop(host.glyphs)
    assert host.runtime.ready and not host.runtime.stopped
