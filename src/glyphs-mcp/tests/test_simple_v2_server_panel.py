"""Exercise the actual dialog controller with explicit worker completion order."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def panel():
    tree = ast.parse((REPO / 'src/bridge/glyphs_mcp_bridge/server_panel.py').read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    pending, writes = [], []
    class Worker:
        def __init__(self, **kwargs): pending.append(kwargs)
        def start(self): pass
    class Control:
        def __init__(self, text=''): self.text, self.enabled = text, True
        def stringValue(self): return self.text
        def setStringValue_(self, value): self.text = value; writes.append(('text', value))
        def setTitle_(self, value): writes.append(('title', value))
        def setTextColor_(self, value): writes.append(('color', value))
        def setState_(self, value): writes.append(('state', value))
        def setEnabled_(self, value): self.enabled = value; writes.append(('enabled', value))
    runtime = SimpleNamespace(ready=True, core=SimpleNamespace(status=lambda: {'activeOperations': 0}))
    env = {'objc': SimpleNamespace(python_method=lambda f: f), 'GeneralPlugin': object,
           'Thread': Worker, 'runtime': runtime, 'AppHelper': SimpleNamespace(callLater=lambda *args: None),
           'AK': SimpleNamespace(NSColor=SimpleNamespace(systemGreenColor=lambda: 'green', secondaryLabelColor=lambda: 'gray'))}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), '<server-panel>', 'exec'), env)
    instance = env['GlyphsMCPServerPlugin']()
    instance.settings()
    for attr in ('status', 'bridge', 'toggle', 'url', 'port', 'auto', 'apply', 'message'):
        setattr(instance, '_' + attr, Control('9680' if attr == 'port' else ''))
    data = {'running': True, 'autoStart': True, 'port': 9680, 'url': 'http://127.0.0.1:9680/mcp/'}
    instance._finish(0, 'status', {'ok': True, 'data': data})
    writes.clear()
    return SimpleNamespace(ui=instance, data=data, pending=pending, writes=writes, runtime=runtime)


def test_repeated_status_polls_never_disable_or_rewrite_unchanged_controls(panel):
    for _ in range(6):
        panel.ui._run('status')
        assert panel.ui._toggle.enabled and panel.ui._port.enabled
        panel.ui._finish(panel.ui._serial, 'status', {'ok': True, 'data': dict(panel.data)})
    assert panel.writes == []


def test_click_during_status_poll_runs_and_late_poll_cannot_overwrite_it(panel):
    panel.ui._run('status')
    stale = panel.ui._serial
    panel.ui._operate('port', '9790')
    assert panel.ui._action == 'port' and not panel.ui._apply.enabled
    panel.ui._finish(stale, 'status', {'ok': True, 'data': {**panel.data, 'running': False}})
    assert panel.ui._action == 'port' and panel.ui._data['running']
    panel.ui._finish(panel.ui._serial, 'port', {'ok': True, 'data': {**panel.data, 'port': 9790}})
    assert panel.ui._action is None and panel.ui._toggle.enabled
    assert panel.ui._data['port'] == 9790


def test_poll_preserves_unsaved_port_text_and_does_not_clear_validation_error(panel):
    panel.ui._port.text = '9790'
    panel.ui._notice = 'Choose another port.'
    panel.ui._finish(0, 'status', {'ok': True, 'data': {**panel.data, 'autoStart': False}})
    assert panel.ui._port.stringValue() == '9790'
    assert panel.ui._message.stringValue() == 'Choose another port.'


def test_port_can_be_changed_back_after_a_successful_apply(panel):
    panel.ui._port.text = '9790'
    panel.ui._operate('port', '9790')
    panel.ui._finish(panel.ui._serial, 'port', {'ok': True, 'data': {**panel.data, 'port': 9790}})
    panel.ui._port.text = '9680'
    panel.ui.applyPort_(None)
    assert panel.pending[-1]['args'][2] == ('9680',)
    assert panel.ui._port.stringValue() == '9680'


def test_port_restart_refuses_to_interrupt_native_writes(panel):
    panel.runtime.core.status = lambda: {'activeOperations': 1}
    panel.ui._operate('port', '9790')
    assert not panel.pending
    assert 'font operation' in panel.ui._message.stringValue()


def test_failed_service_stop_keeps_native_bridge_available(panel):
    stopped = []
    panel.runtime.stop = lambda *_: stopped.append(True)
    panel.ui._operate('stop')
    assert panel.pending[-1]['args'][1] == 'stop'
    panel.ui._finish(panel.ui._serial, 'stop', {'ok': False, 'error': 'Preparation is active'})
    assert stopped == [] and panel.runtime.ready
    assert panel.ui._data['running']


def test_service_stop_can_be_restarted_from_desktop_without_reloading_bridge(panel):
    stopped = []
    panel.runtime.stop = lambda *_: stopped.append(True)
    panel.ui._operate('stop')
    panel.ui._finish(panel.ui._serial, 'stop', {'ok': True, 'data': {**panel.data, 'running': False}})
    assert stopped == [] and panel.runtime.ready


@pytest.mark.parametrize(('action', 'expected'), [('start', 'Starting…'), ('stop', 'Stopping…'), ('port', 'Applying…')])
def test_server_progress_names_the_action_without_claiming_an_update(panel, action, expected):
    panel.ui._run(action)
    assert panel.ui._message.stringValue() == expected
    assert not panel.ui._toggle.enabled
    panel.ui._finish(panel.ui._serial, action, {'ok': True, 'data': panel.data})
    assert panel.ui._toggle.enabled
    assert panel.ui._message.stringValue() != expected
