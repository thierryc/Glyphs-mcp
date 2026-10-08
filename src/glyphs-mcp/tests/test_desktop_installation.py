"""Installation busy refusal cannot become a destructive recovery retry."""
from contextlib import contextmanager, nullcontext
import json
import errno
from pathlib import Path
import plistlib
import sys
from types import SimpleNamespace

import pytest

from test_simple_v2_install import build, install, isolated_service, load_service_controller
import install_simple_v2 as installer
from installation_transaction import InstallationTransaction


@pytest.fixture
def missing_token_service(tmp_path, monkeypatch):
    support = tmp_path/'Library/Application Support/Glyphs MCP'
    state = {'loaded': True, 'commands': []}
    token = support/'bridge-token'
    settings = {'ProgramArguments': ['python', 'run.py']}
    def stop(action):
        assert action == 'stop'
        raise FileNotFoundError(errno.ENOENT, 'No such file or directory', str(token))
    def launch(*args):
        state['commands'].append(args)
        state['loaded'] = False
        return SimpleNamespace(returncode=0, stderr='')
    controller = SimpleNamespace(support=support, domain='gui/123', _run=stop,
        _plist=lambda: settings, status=lambda: {'loaded': state['loaded']}, _launchctl=launch)
    monkeypatch.setattr(installer, 'require_closed_font_processes', lambda _: None)
    return controller, state, token, settings


def test_missing_token_unloads_stale_agent_and_reports_recovery(missing_token_service, capsys):
    controller, state, _, _ = missing_token_service
    installer.stop_for_install(controller, Path('/Applications/Glyphs 4.app'))
    assert state['commands'] == [('bootout', 'gui/123/'+installer.LABEL)]
    assert not state['loaded']
    assert 'continuing installation' in capsys.readouterr().err


def test_install_continues_after_real_controller_reports_missing_token(tmp_path, monkeypatch, capsys):
    output = tmp_path/'build'; build(output)
    app = tmp_path/'Glyphs.app'; (app/'Contents').mkdir(parents=True)
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'com.GeorgSeifert.Glyphs4'}))
    home = tmp_path/'home'
    install(output, home, Path(sys.executable), app)
    controller = load_service_controller(output, home)
    state = {'loaded': True, 'stops': 0}
    def launch(*args):
        if args[0] == 'bootout':
            state.update(loaded=False, stops=state['stops']+1)
        return SimpleNamespace(returncode=0 if state['loaded'] or args[0] != 'print' else 113,
                               stdout='pid = 123' if state['loaded'] else '', stderr='')
    monkeypatch.setattr(controller, '_launchctl', launch)
    # A pre-existing listener triggers the actual token-file read in idle().
    monkeypatch.setattr(controller, 'status', lambda: {
        'loaded': state['loaded'], 'running': state['loaded'],
        'processRunning': state['loaded'], 'processId': 123, 'port': 9680})
    monkeypatch.setattr(installer, 'service_controller', lambda *_: controller)
    monkeypatch.setattr(installer, 'require_closed_font_processes', lambda _: None)
    result = install(output, home, Path(sys.executable), app)
    assert result['components'] == ['mcp']
    assert state == {'loaded': False, 'stops': 1}
    assert 'continuing installation' in capsys.readouterr().err
    assert not (controller.support/'bridge-token').exists()


def test_missing_token_recovery_preserves_finished_job_history(missing_token_service):
    controller, state, _, _ = missing_token_service
    path = controller.support/'lean-v2/jobs/job_test/state.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'status': 'completed'}))
    original = path.read_bytes()
    installer.stop_for_install(controller, Path('/Applications/Glyphs 4.app'))
    assert not state['loaded'] and path.read_bytes() == original


def test_missing_token_recovery_reports_failed_bootout(missing_token_service):
    controller, state, _, _ = missing_token_service
    controller._launchctl = lambda *_: SimpleNamespace(returncode=1, stderr='bootout refused')
    with pytest.raises(RuntimeError, match='bootout refused'):
        installer.stop_for_install(controller, Path('/Applications/Glyphs 4.app'))
    assert state['loaded']


@pytest.mark.parametrize('contents', [None, '{invalid', '[]'])
def test_missing_token_recovery_requires_readable_job_records(missing_token_service, contents):
    controller, state, _, _ = missing_token_service
    path = controller.support/'lean-v2/jobs/job_test/state.json'
    path.parent.mkdir(parents=True)
    if contents is not None:
        path.write_text(contents)
    with pytest.raises(RuntimeError, match='could not be verified'):
        installer.stop_for_install(controller, Path('/Applications/Glyphs 4.app'))
    assert not state['commands'] and state['loaded']


@pytest.mark.parametrize('status', ['preparing', 'applying', 'accepting', 'discarding',
                                   'ready', 'applied', 'failed', 'unknown'])
def test_missing_token_does_not_stop_unfinished_jobs(missing_token_service, status):
    controller, state, _, _ = missing_token_service
    path = controller.support/'lean-v2/jobs/job_test/state.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'status': status}))
    with pytest.raises(RuntimeError, match='unfinished font tasks'):
        installer.stop_for_install(controller, Path('/Applications/Glyphs 4.app'))
    assert state['commands'] == [] and state['loaded']


@pytest.mark.parametrize('kind,status', [('script', 'cancelled'), ('historical_restore', 'interrupted')])
def test_missing_token_preserves_unresolved_native_jobs(missing_token_service, kind, status):
    controller, state, _, _ = missing_token_service
    path = controller.support/'lean-v2/jobs/job_test/state.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'status': status, 'resultKind': kind}))
    with pytest.raises(RuntimeError, match='unfinished font tasks'):
        installer.stop_for_install(controller, Path('/Applications/Glyphs 4.app'))
    assert not state['commands']


def test_missing_token_rechecks_live_font_processes(missing_token_service, monkeypatch):
    controller, state, _, _ = missing_token_service
    def running(_): raise ValueError('Close Glyphs')
    monkeypatch.setattr(installer, 'require_closed_font_processes', running)
    with pytest.raises(ValueError, match='Close Glyphs'):
        installer.stop_for_install(controller, Path('/Applications/Glyphs 4.app'))
    assert not state['commands']


def test_missing_other_file_does_not_trigger_service_recovery(missing_token_service):
    controller, state, _, _ = missing_token_service
    def missing(_): raise FileNotFoundError(errno.ENOENT, 'missing', '/other/file')
    controller._run = missing
    with pytest.raises(FileNotFoundError):
        installer.stop_for_install(controller, Path('/Applications/Glyphs 4.app'))
    assert not state['commands']


def test_missing_custom_token_and_custom_jobs_are_respected(missing_token_service, tmp_path):
    controller, state, _, settings = missing_token_service
    token = tmp_path/'custom-token'; jobs = tmp_path/'custom-jobs'
    settings.update(EnvironmentVariables={'GLYPHS_MCP_BRIDGE_TOKEN_FILE': str(token)},
                    ProgramArguments=['python', 'run.py', '--jobs', str(jobs)])
    def missing(_): raise FileNotFoundError(errno.ENOENT, 'missing', str(token))
    controller._run = missing
    path = jobs/'job_test/state.json'; path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'status': 'applying'}))
    with pytest.raises(RuntimeError, match='unfinished font tasks'):
        installer.stop_for_install(controller, Path('/Applications/Glyphs 4.app'))
    assert not state['commands']


@pytest.mark.parametrize('returncode', [0, 1, 2])
def test_install_process_check_fails_closed(monkeypatch, returncode):
    monkeypatch.setattr(installer.subprocess, 'run', lambda *_, **__: SimpleNamespace(returncode=returncode))
    if returncode == 1:
        installer.require_closed_font_processes(Path('/Applications/Glyphs 4.app'))
    else:
        with pytest.raises((ValueError, RuntimeError)):
            installer.require_closed_font_processes(Path('/Applications/Glyphs 4.app'))


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
