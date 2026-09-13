"""Server settings operate only on the installed local LaunchAgent."""
import plistlib
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'src/sidecar'))
sys.path.insert(0, str(REPO / 'src/protocol'))
from glyphs_mcp_sidecar import control


@pytest.fixture
def server(tmp_path, monkeypatch):
    instance = control.ServerControl(tmp_path)
    instance.agent.parent.mkdir(parents=True)
    settings = {'ProgramArguments': ['python', 'run.py', '--transport', 'http'],
                'RunAtLoad': True, 'KeepAlive': True, 'Unrelated': 'preserve'}
    instance.agent.write_bytes(plistlib.dumps(settings))
    state = {'loaded': True, 'running': True, 'commands': []}
    def launch(*args):
        state['commands'].append(args)
        if args[0] == 'bootout':
            state.update(loaded=False, running=False)
        elif args[0] == 'bootstrap':
            state.update(loaded=True, running=instance._plist()['RunAtLoad'])
        elif args[0] == 'kickstart':
            state.update(loaded=True, running=True)
        return SimpleNamespace(returncode=0 if state['loaded'] or args[0] != 'print' else 113,
                               stdout='pid = 123' if state['running'] else '', stderr='')
    monkeypatch.setattr(instance, '_launchctl', launch)
    state['management'] = []
    def manage(port, action, **values):
        state['management'].append((port, action, values))
        return {'reservationId': 'test-owner', 'expiresInSeconds': 30, 'processId': 123} if action == 'reserve' else {'released': True}
    monkeypatch.setattr(instance, '_management', manage)
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): pass
    monkeypatch.setattr(control.socket, 'create_connection', lambda *_, **__: Connection())
    return instance, state


def test_stop_unloads_keepalive_job_and_start_bootstraps_it(server):
    instance, state = server
    assert instance.run('stop')['running'] is False
    assert ('bootout', instance.domain + '/' + control.LABEL) in state['commands']
    assert instance.run('start')['running'] is True
    assert ('bootstrap', instance.domain, str(instance.agent)) in state['commands']


def test_start_running_server_is_idempotent(server):
    instance, state = server
    assert instance.run('start')['running']
    assert [cmd[0] for cmd in state['commands']] == ['print']


def test_manual_start_works_when_automatic_start_is_disabled(server):
    instance, state = server
    instance.run('auto-off')
    instance.run('stop')
    result = instance.run('start')
    assert result['running'] is True
    assert result['autoStart'] is False
    assert ('kickstart', instance.domain + '/' + control.LABEL) in state['commands']


def test_automatic_start_changes_next_login_without_stopping_running_server(server):
    instance, state = server
    assert instance.run('auto-off')['autoStart'] is False
    settings = plistlib.loads(instance.agent.read_bytes())
    assert settings['RunAtLoad'] is settings['KeepAlive'] is False
    assert settings['Unrelated'] == 'preserve'
    assert state['running']
    assert instance.run('auto-on')['autoStart'] is True


def test_status_requires_listening_process_not_just_loaded_job(server, monkeypatch):
    instance, state = server
    def refused(*_, **__): raise ConnectionRefusedError()
    monkeypatch.setattr(control.socket, 'create_connection', refused)
    assert instance.status()['running'] is False
    state['running'] = False
    assert instance.status()['loaded'] is True


def test_missing_installation_reports_repair_instruction(tmp_path):
    with pytest.raises(RuntimeError, match='installer'):
        control.ServerControl(tmp_path).status()


@pytest.fixture
def free_port_probe(monkeypatch):
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def setsockopt(self, *_): pass
        def bind(self, address): pass
    monkeypatch.setattr(control.socket, 'socket', lambda *_: Socket())


@pytest.mark.parametrize('port', ['', 'abc', '80', '65536', '9681', '9680.5', '-9000', '９７００'])
def test_invalid_or_reserved_ports_do_not_change_config_or_process(server, port):
    instance, state = server
    original = instance.agent.read_bytes()
    with pytest.raises(ValueError):
        instance.run('port', port)
    assert instance.agent.read_bytes() == original
    assert not state['commands']


def test_port_change_restarts_running_server_and_preserves_other_settings(server, free_port_probe):
    instance, state = server
    result = instance.run('port', '9790')
    assert result['running'] and result['port'] == 9790
    assert result['url'] == 'http://127.0.0.1:9790/mcp/'
    assert instance._plist()['Unrelated'] == 'preserve'
    assert [cmd[0] for cmd in state['commands'] if cmd[0] != 'print'] == ['bootout', 'bootstrap']


def test_port_change_preserves_stopped_state(server, free_port_probe):
    instance, state = server
    instance.run('stop')
    state['commands'].clear()
    result = instance.run('port', '9790')
    assert result['port'] == 9790 and not result['running'] and not result['loaded']
    assert all(cmd[0] == 'print' for cmd in state['commands'])


def test_in_use_port_is_rejected_before_stopping_server(server, monkeypatch):
    instance, state = server
    original = instance.agent.read_bytes()
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def setsockopt(self, *_): pass
        def bind(self, address): raise OSError('Address already in use')
    monkeypatch.setattr(control.socket, 'socket', lambda *_: Socket())
    with pytest.raises(ValueError, match='already in use'):
        instance.run('port', '9790')
    assert instance.agent.read_bytes() == original and state['running']
    assert all(cmd[0] == 'print' for cmd in state['commands'])


def test_restart_failure_restores_previous_port_and_running_server(server, free_port_probe, monkeypatch):
    instance, state = server
    original = instance.agent.read_bytes()
    launch = instance._launchctl
    def fail_new_port(*args):
        if args[0] == 'bootstrap' and '9790' in instance._plist()['ProgramArguments']:
            return SimpleNamespace(returncode=1, stdout='', stderr='Port was claimed during restart')
        return launch(*args)
    monkeypatch.setattr(instance, '_launchctl', fail_new_port)
    with pytest.raises(RuntimeError, match='claimed'):
        instance.run('port', '9790')
    assert instance.agent.read_bytes() == original
    assert instance.status()['port'] == 9680 and state['running']


def test_port_can_return_to_a_closed_listener_with_recent_connections(server):
    instance, _ = server
    with socket.socket() as listener, socket.socket() as client:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0))
        address = listener.getsockname()
        listener.listen()
        client.connect(address)
        connection, _ = listener.accept()
        connection.close()
        assert client.recv(1) == b''
    # The server closed first: its previous connection remains in TIME_WAIT.
    result = instance.run('port', str(address[1]))
    assert result['running'] and result['port'] == address[1]


def test_live_reusable_listener_still_blocks_port_change(server):
    instance, state = server
    original = instance.agent.read_bytes()
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        with pytest.raises(ValueError, match='already in use'):
            instance.run('port', str(listener.getsockname()[1]))
    assert instance.agent.read_bytes() == original and state['running']
    assert all(command[0] == 'print' for command in state['commands'])
