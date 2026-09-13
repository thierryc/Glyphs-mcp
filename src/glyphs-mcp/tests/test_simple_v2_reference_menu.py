"""Current-reference indicators use native menu-open events and per-font state."""

import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3] / 'src/companions/reference-inspector/glyphs_reference_inspector'


@pytest.fixture
def menu_host(monkeypatch):
    class Item:
        @classmethod
        def new(cls): return cls()
        def setTitle_(self, value): self.title = value
        def setTarget_(self, value): self.target = value
        def setAction_(self, value): self.action = value
        def setRepresentedObject_(self, value): self.kind = value
        def setSubmenu_(self, value): self.submenu = value
        def setState_(self, value): self.state = value
        def setToolTip_(self, value): self.tooltip = value
        def setEnabled_(self, value): self.enabled = value

    class Menu:
        @classmethod
        def alloc(cls): return cls()
        def initWithTitle_(self, title): self.items = []; return self
        def setAutoenablesItems_(self, value): self.auto = value
        def setDelegate_(self, value): self.delegate = value
        def addItem_(self, value): self.items.append(value)
        def itemArray(self): return self.items

    host = SimpleNamespace(font=SimpleNamespace(filepath='/fonts/Working.glyphspackage'),
                           menu={'edit': []}, defaults={}, activateReporter=lambda _: None)
    native = SimpleNamespace(NSMenu=Menu, NSMenuItem=Item)
    for name in ('NSAlert', 'NSOpenPanel', 'NSTextField', 'NSView', 'NSMakeRect'):
        setattr(native, name, object)
    monkeypatch.setitem(sys.modules, 'AppKit', native)
    monkeypatch.setitem(sys.modules, 'GlyphsApp', SimpleNamespace(Glyphs=host, EDIT_MENU='edit'))
    spec = importlib.util.spec_from_file_location('reference_menus_test', ROOT / 'menus.py')
    menus = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(menus)
    tree = ast.parse((ROOT / 'plugin.py').read_text())
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))
             and node.name in ('_value', 'GlyphsReferenceInspector')]
    env = {'objc': SimpleNamespace(python_method=lambda f: f, typedSelector=lambda _: lambda f: f),
           'ReporterPlugin': object, 'Glyphs': host, 'menus': menus, 'json': json, 'PREFERENCES': 'test.references',
           'withdraw': lambda _: None, 'MANIFEST': {'id': 'reference-inspector'}}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<reference-plugin>', 'exec'), env)
    owner = env['GlyphsReferenceInspector']()
    owner._specs = {}
    root = menus.install_menu(owner)
    owner._menu = root
    return SimpleNamespace(owner=owner, host=host, root=root, menu=root.submenu, menus=menus)


def open_menu(value):
    value.menu.delegate.menuNeedsUpdate_(value.menu)
    return {item.kind: item for item in value.menu.items}


@pytest.mark.parametrize('kind, reference, detail, tooltip', [
    ('last_saved', {'kind': 'last_saved'}, 'Working.glyphspackage', 'File: /fonts/Working.glyphspackage'),
    ('file', {'kind': 'file', 'source': '/references/Original.glyphs'}, 'Original.glyphs', 'File: /references/Original.glyphs'),
    ('local_git', {'kind': 'local_git', 'source': '/repos/font', 'revision': 'release/2.0', 'fontPath': 'sources/Family.glyphspackage'},
     'Family.glyphspackage @ release/2.0', 'Repository: /repos/font\nRevision: release/2.0\nFont path: sources/Family.glyphspackage'),
    ('github', {'kind': 'github', 'source': 'https://github.com/owner/font', 'revision': 'v2.0', 'fontPath': 'Family.glyphs'},
     'Family.glyphs @ v2.0', 'Repository: https://github.com/owner/font\nRevision: v2.0\nFont path: Family.glyphs'),
])
def test_selected_type_has_one_native_checkmark_and_editable_details(menu_host, kind, reference, detail, tooltip):
    value = menu_host
    value.owner._specs[value.host.font.filepath] = reference
    original_actions = [item.action for item in value.menu.items]
    items = open_menu(value)
    assert [item.kind for item in items.values() if item.state == 1] == [kind]
    assert detail in items[kind].title
    assert items[kind].tooltip == tooltip
    assert all(item.enabled for item in items.values())
    assert [item.action for item in value.menu.items] == original_actions
    assert all(item.target is value.owner for item in value.menu.items)
    if kind != 'last_saved':
        assert items[kind].title.endswith('…')
    assert not items['refresh'].state


def test_opening_menu_reads_the_active_font_and_clears_previous_font_details(menu_host):
    value = menu_host
    value.owner._specs['/fonts/Working.glyphspackage'] = {'kind': 'file', 'source': '/references/Original.glyphs'}
    items = open_menu(value)
    assert items['file'].state == 1
    value.host.font = SimpleNamespace(filepath='/fonts/Other.glyphs')
    items = open_menu(value)
    assert items['last_saved'].state == 1 and 'Other.glyphs' in items['last_saved'].title
    assert items['file'].title == 'Font File…' and items['file'].tooltip is None
    value.host.font = SimpleNamespace(filepath='/fonts/Working.glyphspackage')
    assert open_menu(value)['file'].state == 1


@pytest.mark.parametrize('font, message', [(None, 'Open a font'), (SimpleNamespace(filepath=None), 'Save this font')])
def test_no_font_or_unsaved_font_clears_checks_details_and_disables_commands(menu_host, font, message):
    value = menu_host
    open_menu(value)
    value.host.font = font
    items = open_menu(value)
    assert not any(item.state or item.enabled for item in items.values())
    assert [item.title for item in items.values()] == [title for _, title, _ in value.menus.COMMANDS]
    assert all(message in item.tooltip for item in items.values())
    value.owner._configure({'kind': 'file', 'source': '/references/Original.glyphs'})
    assert not value.owner._specs and not value.host.defaults


def test_menu_refresh_uses_no_timer_worker_or_reference_loading(menu_host):
    value = menu_host
    assert value.menu.auto is False
    assert value.menu.delegate is value.owner
    # No reader, thread, or AppHelper is supplied to this real controller.
    for _ in range(5):
        assert open_menu(value)['last_saved'].state == 1
    assert not value.host.defaults


def test_long_revision_and_filename_are_compact_but_tooltip_keeps_full_values(menu_host):
    value = menu_host
    revision = 'feature/' + 'long-name-' * 10
    path = 'nested/' + 'LongFontName' * 10 + '.glyphspackage'
    value.owner._specs[value.host.font.filepath] = {'kind': 'github', 'source': 'https://github.com/owner/font',
                                                 'revision': revision, 'fontPath': path}
    item = open_menu(value)['github']
    assert len(item.title) < 90 and item.title.endswith('…')
    assert revision in item.tooltip and path in item.tooltip


def test_implicit_git_defaults_are_shown_without_resolving_git(menu_host):
    value = menu_host
    value.owner._specs[value.host.font.filepath] = {'kind': 'local_git'}
    item = open_menu(value)['local_git']
    assert 'Working.glyphspackage @ HEAD' in item.title
    assert 'Repository: /fonts' in item.tooltip
    assert '/fonts/Working.glyphspackage' in item.tooltip


def test_selected_chooser_action_still_opens_editor(menu_host, monkeypatch):
    value = menu_host
    reference = {'kind': 'github', 'source': 'https://github.com/owner/font', 'revision': 'main', 'fontPath': 'Font.glyphs'}
    value.owner._specs[value.host.font.filepath] = reference
    calls = []
    monkeypatch.setattr(value.menus, 'choose_git', lambda kind, previous: calls.append((kind, previous)))
    item = open_menu(value)['github']
    item.action(item)
    assert calls == [('github', reference)]
