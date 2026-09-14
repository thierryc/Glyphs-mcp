"""Installation busy refusal cannot become a destructive recovery retry."""
from contextlib import contextmanager, nullcontext
import json
from pathlib import Path
import plistlib
import sys
from types import SimpleNamespace

import pytest

from test_simple_v2_install import build, install, isolated_service
import install_simple_v2 as installer
from installation_transaction import InstallationTransaction


def test_failed_verification_stops_replacement_before_restoring_files(tmp_path):
    target, source = tmp_path/'installed', tmp_path/'new'
    target.write_text('old'); source.write_text('new')
    transaction = InstallationTransaction(tmp_path, [(source, target)])
    observations = []
    def failed_verification():
        raise RuntimeError('verification failed')
    def stop():
        observations.append(target.read_text())
    with pytest.raises(RuntimeError, match='verification failed'):
        transaction.apply(failed_verification, before_rollback=stop)
    assert observations == ['new']
    assert target.read_text() == 'old'


def test_failed_stop_retains_recovery_material_and_does_not_replace_running_code(tmp_path):
    target, source = tmp_path/'installed', tmp_path/'new'
    target.write_text('old'); source.write_text('new')
    transaction = InstallationTransaction(tmp_path, [(source, target)])
    def fail():
        raise RuntimeError('stop failed')
    with pytest.raises(RuntimeError, match='stop failed'):
        transaction.apply(fail, before_rollback=fail)
    assert target.read_text() == 'new'
    assert (transaction.backup/'installed').read_text() == 'old'
    InstallationTransaction.recover(tmp_path, {target})
    assert target.read_text() == 'old'


@pytest.mark.parametrize('start', [True, False])
def test_rejected_busy_install_and_retry_preserve_files_and_running_service(tmp_path, monkeypatch, start):
    output = tmp_path/'build'; build(output)
    app = tmp_path/'Glyphs.app'; (app/'Contents').mkdir(parents=True)
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.GeorgSeifert.Glyphs4'}))
    home = tmp_path/'home'
    first = install(output, home, Path(sys.executable), app)
    root = home/'Library/Application Support/Glyphs MCP/lean-v2'
    receipt = (root/'installation.json').read_bytes()
    agent = Path(first['launchAgent']); settings = agent.read_bytes()
    stopped, restarted = [], []
    def busy(action):
        stopped.append(action)
        raise RuntimeError('The service is busy')
    controller = SimpleNamespace(agent=agent, exclusive=nullcontext, status=lambda: {'loaded':True}, _run=busy)
    monkeypatch.setattr(installer, 'service_controller', lambda *_: controller)
    monkeypatch.setattr(installer, 'restart_agent', lambda *_: restarted.append(True))
    for _ in range(2):
        with pytest.raises(RuntimeError, match='busy'):
            install(output, home, Path(sys.executable), app, start=start)
        assert agent.read_bytes() == settings
        assert (root/'installation.json').read_bytes() == receipt
        assert restarted == []
    assert stopped == ['stop','stop']
    assert all(json.loads(path.read_text())['state'] in ('committed','restored') for path in root.glob('transaction-*/journal.json'))


def test_installed_agent_has_one_supervisor_and_desktop_identity(tmp_path):
    output = tmp_path/'build'; build(output)
    app = tmp_path/'Glyphs.app'; (app/'Contents').mkdir(parents=True)
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.GeorgSeifert.Glyphs4'}))
    home = tmp_path/'home'
    receipt = install(output, home, Path(sys.executable), app)
    agent = plistlib.loads(Path(receipt['launchAgent']).read_bytes())
    assert agent['AssociatedBundleIdentifiers'] == ['cx.ap.glyphsMcp']
    assert agent['Label'] == 'com.ap.cx.glyphs-mcp-sidecar'
    assert len(list((home/'Library/LaunchAgents').glob('*.plist'))) == 1


@pytest.mark.parametrize('action', ['upgrade', 'remove', 'failed-upgrade'])
def test_no_start_install_stops_idle_service_and_restores_it_only_on_failure(tmp_path, monkeypatch, action):
    output = tmp_path/'build'; build(output)
    app = tmp_path/'Glyphs.app'; (app/'Contents').mkdir(parents=True)
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.GeorgSeifert.Glyphs4'}))
    home = tmp_path/'home'
    first = install(output, home, Path(sys.executable), app)
    root = home/'Library/Application Support/Glyphs MCP/lean-v2'
    receipt = (root/'installation.json').read_bytes()
    agent = Path(first['launchAgent']); original_agent = agent.read_bytes()
    state = {'loaded': True, 'locked': False, 'events': []}
    @contextmanager
    def exclusive():
        state['locked'] = True
        try: yield
        finally: state['locked'] = False
    def stop(command):
        assert command == 'stop' and state['locked']
        state['events'].append(command); state['loaded'] = False
    def restart(*_):
        assert state['locked']
        state['events'].append('restart'); state['loaded'] = True
    controller = SimpleNamespace(agent=agent, exclusive=exclusive,
        status=lambda: {'loaded':state['loaded']}, _run=stop)
    monkeypatch.setattr(installer, 'service_controller', lambda *_: controller)
    monkeypatch.setattr(installer, 'restart_agent', restart)
    if action == 'failed-upgrade':
        identity = installer._identity
        def fail(path):
            if Path(path) == root/'sidecar': raise RuntimeError('verification failed')
            return identity(path)
        monkeypatch.setattr(installer, '_identity', fail)
        with pytest.raises(RuntimeError, match='verification failed'):
            install(output, home, Path(sys.executable), app, start=False)
        assert state['events'] == ['stop', 'restart'] and state['loaded']
        assert agent.read_bytes() == original_agent and (root/'installation.json').read_bytes() == receipt
    else:
        removal = {'mcp':False, 'remove_components':['mcp']} if action == 'remove' else {}
        install(output, home, Path(sys.executable), app, start=False, **removal)
        assert state['events'] == ['stop'] and not state['loaded']
        assert agent.exists() == (action == 'upgrade')
    assert not state['locked']
