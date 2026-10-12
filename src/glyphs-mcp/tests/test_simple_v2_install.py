"""Local evaluation install preserves unrelated plugins and replacement backups."""
import json
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO/'scripts'))
from build_simple_v2 import build
from install_simple_v2 import install, service_controller as load_service_controller


def test_packaged_installer_imports_sibling_helpers_in_isolated_mode(tmp_path):
    packaged = tmp_path / 'Payload' / 'Installer'
    packaged.mkdir(parents=True)
    for name in ('install_simple_v2.py', 'build_simple_v2.py', 'installation_transaction.py'):
        shutil.copy2(REPO / 'scripts' / name, packaged / name)
    result = subprocess.run(
        [sys.executable, '-I', '-B', str(packaged / 'install_simple_v2.py'), '--help'],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert '--preflight-only' in result.stdout


@pytest.fixture(autouse=True)
def isolated_service(monkeypatch):
    import install_simple_v2 as installer
    def controller(build, home):
        return SimpleNamespace(agent=Path(home)/'Library/LaunchAgents'/f'{installer.LABEL}.plist',
                               exclusive=nullcontext, status=lambda: {'loaded': False})
    monkeypatch.setattr(installer, 'service_controller', controller)


def test_loading_verified_controls_does_not_modify_payload_identity(tmp_path, monkeypatch):
    from build_simple_v2 import _identity
    output = tmp_path/'build'; build(output)
    before = _identity(output/'sidecar')
    monkeypatch.setattr(sys, 'dont_write_bytecode', False)
    controller = load_service_controller(output, tmp_path/'home')
    assert controller.agent.name == 'com.ap.cx.glyphs-mcp-sidecar.plist'
    assert _identity(output/'sidecar') == before


def test_bridge_only_then_optional_companions_preserve_previous_install(tmp_path):
    output = tmp_path/'build'
    build(output)
    home = tmp_path/'home'
    app = tmp_path/'Glyphs.app'
    (app/'Contents').mkdir(parents=True)
    with (app/'Contents/Info.plist').open('wb') as stream:
        plistlib.dump({'CFBundleIdentifier':'com.GeorgSeifert.Glyphs4'},stream)
    plugins = home/'Library/Application Support/Glyphs 4/Plugins'
    plugins.mkdir(parents=True)
    unrelated = plugins/'IconGrid.glyphsReporter'
    unrelated.write_text('leave untouched')
    legacy = plugins/'Glyphs MCP Bridge.glyphsPalette'
    legacy.mkdir()
    (legacy/'old').write_text('previous palette')
    first = install(output,home,Path(sys.executable),app)
    assert not legacy.exists()
    assert (Path(first['backup'])/legacy.name/'old').read_text() == 'previous palette'
    assert len(first['installed']) == 2
    manifest = json.loads((output/'manifest.json').read_text())
    assert first['sidecar']['codeHash'] == manifest['sidecar']['codeHash']
    assert first['sidecar']['glyphDiffReader'] == manifest['glyphDiffReader'] == {
        'schemaVersion': 3,
        'protocolAPIVersion': 1,
        'workerModule': 'glyphs_mcp_sidecar.glyph_diff_worker',
    }
    assert first['bridge']['codeHash'] == manifest['bridge']['codeHash']
    assert first['bridgeVersion'] == manifest['projectVersion']
    assert not (plugins/'Glyphs Reference Inspector.glyphsReporter').exists()
    second = install(output,home,Path(sys.executable),app,['curve-inspector','reference-inspector'])
    assert len(second['installed']) == 4
    assert (Path(second['backup'])/'Glyphs MCP Bridge.glyphsPlugin').is_dir()
    assert (plugins/'Glyphs Reference Inspector.glyphsReporter/Contents/Resources/reference_core/native_worker.py').is_file()
    assert unrelated.read_text() == 'leave untouched'
    with Path(second['launchAgent']).open('rb') as stream:
        agent = plistlib.load(stream)
    assert agent['ProgramArguments'][-1] == str(app)
    assert agent['ProgramArguments'][2:4] == ['--transport','http']


def test_tampered_build_refused_before_install(tmp_path):
    output=tmp_path/'build'
    build(output)
    (output/'sidecar/run.py').write_text('changed')
    app=tmp_path/'Glyphs.app'
    (app/'Contents').mkdir(parents=True)
    with (app/'Contents/Info.plist').open('wb') as stream:
        plistlib.dump({'CFBundleIdentifier':'com.GeorgSeifert.Glyphs4'},stream)
    with pytest.raises(ValueError,match='identity mismatch'):
        install(output,tmp_path/'home',Path(sys.executable),app)
    assert not (tmp_path/'home').exists()


@pytest.mark.parametrize('automatic', [True, False])
def test_launchagent_restart_retries_asynchronous_bootout(monkeypatch, tmp_path, automatic):
    import install_simple_v2 as installer
    from types import SimpleNamespace
    codes=iter([0,5,0,0]);commands=[]
    def run(command,**kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=next(codes),stderr='label is unloading')
    monkeypatch.setattr(installer.subprocess,'run',run)
    monkeypatch.setattr(installer.time,'sleep',lambda delay: None)
    agent = tmp_path / 'agent.plist'
    agent.write_bytes(plistlib.dumps({'RunAtLoad': automatic}))
    installer.restart_agent(agent,504)
    assert [command[1] for command in commands] == ['bootout','bootstrap','bootstrap'] + ([] if automatic else ['kickstart'])


def test_reinstall_preserves_disabled_automatic_start(tmp_path):
    output = tmp_path / 'build'; build(output)
    home = tmp_path / 'home'; app = tmp_path / 'Glyphs.app'
    (app / 'Contents').mkdir(parents=True)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.GeorgSeifert.Glyphs4'}))
    first = install(output, home, Path(sys.executable), app)
    path = Path(first['launchAgent']); agent = plistlib.loads(path.read_bytes())
    agent.update(RunAtLoad=False, KeepAlive=False); path.write_bytes(plistlib.dumps(agent))
    agent['ProgramArguments'][agent['ProgramArguments'].index('--port') + 1] = '9790'
    path.write_bytes(plistlib.dumps(agent))
    install(output, home, Path(sys.executable), app)
    installed = plistlib.loads(path.read_bytes())
    assert installed['RunAtLoad'] is False
    assert installed['ProgramArguments'][installed['ProgramArguments'].index('--port') + 1] == '9790'


def fixture_install(tmp_path):
    output=tmp_path/'build'; build(output)
    app=tmp_path/'Glyphs.app'; (app/'Contents').mkdir(parents=True)
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.GeorgSeifert.Glyphs4'}))
    return output, tmp_path/'home', app


@pytest.mark.parametrize('remaining', [[], ['curve-inspector']])
def test_remove_and_reinstall_retains_service_preferences(tmp_path, remaining):
    from install_simple_v2 import COMPONENTS
    output, home, app = fixture_install(tmp_path)
    first = install(output, home, Path(sys.executable), app, ['curve-inspector', 'reference-inspector'])
    agent_path = Path(first['launchAgent'])
    agent = plistlib.loads(agent_path.read_bytes())
    agent['ProgramArguments'][agent['ProgramArguments'].index('--port') + 1] = '9790'
    agent.update(RunAtLoad=False, KeepAlive=False)
    agent_path.write_bytes(plistlib.dumps(agent))
    token = home/'Library/Application Support/Glyphs MCP/bridge-token'
    token.write_text('test authentication')
    removed = install(output, home, None, app, mcp=False,
                      remove_components=set(COMPONENTS)-set(remaining))
    assert removed['port'] == 9790 and removed['autoStart'] is False
    assert not agent_path.exists()
    # Another component-only transaction must keep the remembered settings.
    install(output, home, None, app, remaining, mcp=False)
    installed = install(output, home, Path(sys.executable), app)
    restored = plistlib.loads(agent_path.read_bytes())
    assert installed['port'] == 9790 and installed['autoStart'] is False
    assert restored['ProgramArguments'][restored['ProgramArguments'].index('--port') + 1] == '9790'
    assert restored['RunAtLoad'] is False and restored['KeepAlive'] is False
    assert token.read_text() == 'test authentication'


@pytest.mark.parametrize('mask', range(1, 8))
def test_all_component_combinations_can_be_installed_independently(tmp_path, mask):
    from install_simple_v2 import COMPONENTS
    output, home, app = fixture_install(tmp_path)
    selected={name for i,name in enumerate(COMPONENTS) if mask & (1 << i)}
    result=install(output,home,Path(sys.executable),app, selected-{'mcp'}, mcp='mcp' in selected)
    assert set(result['components']) == selected
    plugins=home/'Library/Application Support/Glyphs 4/Plugins'
    assert len(list(plugins.iterdir())) == len(selected)
    assert (result['launchAgent'] is not None) == ('mcp' in selected)


def test_explicit_removal_preserves_remaining_companions_and_preferences(tmp_path):
    output, home, app = fixture_install(tmp_path)
    first=install(output,home,Path(sys.executable),app,['curve-inspector','reference-inspector'])
    token=home/'Library/Application Support/Glyphs MCP/token'; token.write_text('auth')
    preference=home/'Library/Preferences/com.GeorgSeifert.Glyphs4.plist'; preference.parent.mkdir()
    preference.write_bytes(plistlib.dumps({'welcomeShown':True,'port':9790}))
    before=preference.read_bytes()
    result=install(output,home,Path(sys.executable),app,mcp=False,remove_components=['mcp'])
    assert set(result['components']) == {'curve-inspector','reference-inspector'}
    assert not Path(first['launchAgent']).exists()
    assert not (Path(first['launchAgent']).parents[1]/'Application Support/Glyphs MCP/lean-v2/sidecar').exists()
    assert token.read_text() == 'auth' and preference.read_bytes() == before
    result=install(output,home,None,app,mcp=False,remove_components=['curve-inspector','reference-inspector'])
    assert result['components'] == [] and result['launchAgent'] is None


def test_scoped_update_and_removal_never_replace_unrelated_components(tmp_path):
    from build_simple_v2 import _identity
    output, home, app = fixture_install(tmp_path)
    install(output, home, Path(sys.executable), app, ['curve-inspector', 'reference-inspector'])
    plugins = home/'Library/Application Support/Glyphs 4/Plugins'
    paths = {
        'mcp': plugins/'Glyphs MCP Bridge.glyphsPlugin',
        'curve-inspector': plugins/'Glyphs Curve Inspector.glyphsReporter',
        'reference-inspector': plugins/'Glyphs Reference Inspector.glyphsReporter',
    }
    before = {name: _identity(path) for name, path in paths.items()}

    updated = install(output, home, Path(sys.executable), app, ['curve-inspector'], mcp=False,
                      only_components=['curve-inspector'])
    assert set(updated['components']) == set(paths)
    assert _identity(paths['mcp']) == before['mcp']
    assert _identity(paths['reference-inspector']) == before['reference-inspector']

    removed = install(output, home, Path(sys.executable), app, mcp=False,
                      remove_components=['curve-inspector'], only_components=['curve-inspector'])
    assert set(removed['components']) == {'mcp', 'reference-inspector'}
    assert not paths['curve-inspector'].exists()
    assert _identity(paths['mcp']) == before['mcp']
    assert _identity(paths['reference-inspector']) == before['reference-inspector']

    root = home/'Library/Application Support/Glyphs MCP/lean-v2'
    runtime = root/'runtime'
    runtime.mkdir()
    (runtime/'marker').write_text('shared with reference inspector')
    receipt_path = root/'installation.json'
    receipt = json.loads(receipt_path.read_text())
    runtime_record = {'path': str(runtime), 'identity': _identity(runtime)}
    receipt['installed'].append(runtime_record)
    receipt['runtime'] = {'identity': runtime_record['identity']}
    receipt_path.write_text(json.dumps(receipt))
    reference_identity = _identity(paths['reference-inspector'])
    reference_only = install(output, home, Path(sys.executable), app, mcp=False,
                             remove_components=['mcp'], only_components=['mcp'])
    assert set(reference_only['components']) == {'reference-inspector'}
    assert runtime.is_dir()
    assert next(item for item in reference_only['installed'] if item['path'] == str(runtime)) == runtime_record
    assert _identity(paths['reference-inspector']) == reference_identity


def test_failed_upgrade_restores_agent_receipt_components_and_unrelated_files(tmp_path, monkeypatch):
    import install_simple_v2 as installer
    from build_simple_v2 import _identity
    output, home, app = fixture_install(tmp_path)
    install(output,home,Path(sys.executable),app,['curve-inspector','reference-inspector'])
    # File changes after replacement include the final installation record.
    paths=[home/'Library/Application Support/Glyphs 4/Plugins',home/'Library/LaunchAgents']
    root=home/'Library/Application Support/Glyphs MCP/lean-v2'
    before={p:_identity(p) for p in paths}; receipt=(root/'installation.json').read_bytes()
    original=installer._identity
    def fail_installed(path):
        if Path(path) == root/'sidecar': raise RuntimeError('verification failed')
        return original(path)
    monkeypatch.setattr(installer,'_identity',fail_installed)
    with pytest.raises(RuntimeError,match='verification failed'):
        install(output,home,Path(sys.executable),app,['curve-inspector','reference-inspector'])
    assert {p:_identity(p) for p in paths} == before
    assert (root/'installation.json').read_bytes() == receipt


def test_interrupted_upgrade_recovers_receipt_before_choosing_components(tmp_path):
    import json
    from installation_transaction import InstallationTransaction
    output, home, app = fixture_install(tmp_path)
    install(output,home,None,app,['curve-inspector'],mcp=False)
    root=home/'Library/Application Support/Glyphs MCP/lean-v2'; receipt=root/'installation.json'
    damaged=tmp_path/'new-receipt'; damaged.write_text(json.dumps({'components':['mcp']}))
    transaction=InstallationTransaction(root,[(damaged,receipt)])
    transaction.data['state']='applying'; transaction.data['entries'][0]['started']=True
    transaction.journal.write_text(json.dumps(transaction.data))
    receipt.rename(transaction.backup/receipt.name); Path(transaction.data['entries'][0]['stage']).rename(receipt)
    result=install(output,home,None,app,mcp=False)
    assert result['components'] == ['curve-inspector']


def test_native_python_preflight_keeps_application_imports_read_only(tmp_path, monkeypatch):
    import install_simple_v2 as installer
    output = tmp_path / 'payload'
    helper = output / 'sidecar/glyphs_mcp_protocol/python_runtime.py'
    helper.parent.mkdir(parents=True)
    shutil.copy2(REPO / 'src/protocol/glyphs_mcp_protocol/python_runtime.py', helper)
    cli = output / 'runtime/bin/glyphs'
    cli.parent.mkdir(parents=True)
    (output / 'manifest.json').write_text(json.dumps({'runtimes': {
        installer.platform.machine(): {'path': 'runtime', 'glyphsCLI': 'bin/glyphs'}
    }}))
    app = tmp_path / 'Glyphs 4.app'
    scripts = app / 'Contents/Scripts'
    scripts.mkdir(parents=True)
    (scripts / 'native_probe.py').write_text('ready = True\n')
    cli.write_text(f'#!{sys.executable}\n' + '''import os, sys
from pathlib import Path
assert os.environ['PYTHONDONTWRITEBYTECODE'] == '1'
assert os.environ['PYTHONNOUSERSITE'] == '1'
assert os.environ['GLYPHS_PREFLIGHT_TEST_INHERITED'] == 'preserved'
app = Path(sys.argv[sys.argv.index('--app') + 1])
sys.path.insert(0, str(app / 'Contents/Scripts'))
import native_probe
assert native_probe.ready
print('GLYPHS_MCP_NATIVE_READY:3.14.6')
''')
    cli.chmod(0o755)
    monkeypatch.setenv('PYTHONDONTWRITEBYTECODE', '0')
    monkeypatch.setenv('PYTHONNOUSERSITE', '0')
    monkeypatch.setenv('GLYPHS_PREFLIGHT_TEST_INHERITED', 'preserved')
    assert installer.preflight(output, app) == '3.14.6'
    assert not list(app.rglob('__pycache__'))


def test_native_python_preflight_reports_glyphs_version_and_rejects_missing_configuration(tmp_path, monkeypatch):
    import install_simple_v2 as installer
    output = tmp_path / 'payload'
    output.mkdir()
    helper = output / 'sidecar/glyphs_mcp_protocol/python_runtime.py'
    helper.parent.mkdir(parents=True)
    shutil.copy2(REPO / 'src/protocol/glyphs_mcp_protocol/python_runtime.py', helper)
    (output / 'manifest.json').write_text(json.dumps({'runtimes': {
        installer.platform.machine(): {'path': 'runtime', 'glyphsCLI': 'bin/glyphs'}
    }}))
    app = tmp_path / 'Glyphs 4.app'
    calls = []
    def ready(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='GLYPHS_MCP_NATIVE_READY:3.14.6\n', stderr='')
    monkeypatch.setattr(installer.subprocess, 'run', ready)
    assert installer.preflight(output, app) == '3.14.6'
    assert calls[0][calls[0].index('--app') + 1] == str(app)
    monkeypatch.setattr(installer.subprocess, 'run', lambda *a, **k:
        SimpleNamespace(returncode=1, stdout='', stderr='No Python framework path configured.'))
    with pytest.raises(ValueError, match='Plugin Manager → Modules') as failure:
        installer.preflight(output, app)
    assert 'No Python framework path configured' in str(failure.value)
    assert not (tmp_path / 'home').exists()


def test_explicit_python_check_override_installs_components_with_unverified_scripting(tmp_path, monkeypatch, capsys):
    import install_simple_v2 as installer
    output, home, app = fixture_install(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['install_simple_v2.py', '--build', str(output), '--home', str(home),
        '--glyphs-app', str(app), '--python', sys.executable, '--skip-python-check'])
    monkeypatch.setattr(installer, 'preflight', lambda *a: pytest.fail('Python check was explicitly skipped'))
    checks = []
    monkeypatch.setattr(installer, 'require_closed_font_processes', lambda application: checks.append(application))
    installer.main()
    captured = capsys.readouterr()
    assert 'readiness remains unverified' in captured.err
    result = json.loads(captured.out)
    assert result['components'] == ['mcp']
    assert checks == [app]
    assert (home / 'Library/Application Support/Glyphs 4/Plugins/Glyphs MCP Bridge.glyphsPlugin').is_dir()


@pytest.mark.parametrize('arguments', [[], ['--preflight-only', '--skip-python-check']])
def test_check_still_fails_without_override_and_preflight_only_cannot_be_skipped(tmp_path, monkeypatch, arguments):
    import install_simple_v2 as installer
    output, home, app = fixture_install(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['install_simple_v2.py', '--build', str(output), '--home', str(home),
        '--glyphs-app', str(app), *arguments])
    def failed(*args): raise ValueError('Glyphs scripting is not ready')
    monkeypatch.setattr(installer, 'preflight', failed)
    monkeypatch.setattr(installer, 'require_closed_font_processes', lambda *a: pytest.fail('Must check Python first'))
    with pytest.raises(ValueError, match='scripting is not ready'):
        installer.main()
    assert not (home / 'Library/Application Support/Glyphs MCP/lean-v2/installation.json').exists()


@pytest.mark.parametrize('failure', ['running-glyphs', 'invalid-payload'])
def test_python_override_preserves_process_and_payload_guards(tmp_path, monkeypatch, failure):
    import install_simple_v2 as installer
    output, home, app = fixture_install(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['install_simple_v2.py', '--build', str(output), '--home', str(home),
        '--glyphs-app', str(app), '--python', sys.executable, '--skip-python-check'])
    monkeypatch.setattr(installer, 'preflight', lambda *a: pytest.fail('Python check was explicitly skipped'))
    def check(application):
        if failure == 'running-glyphs': raise ValueError('Close Glyphs before installing')
    monkeypatch.setattr(installer, 'require_closed_font_processes', check)
    if failure == 'invalid-payload':
        (output / 'sidecar/run.py').write_text('corrupted payload')
    with pytest.raises(ValueError, match='Close Glyphs|Build identity mismatch'):
        installer.main()
    assert not (home / 'Library/Application Support/Glyphs MCP/lean-v2/installation.json').exists()


@pytest.mark.parametrize('identifier,version', [('com.GeorgSeifert.Glyphs4Beta','4.2'),('com.GeorgSeifert.GlyphsBeta','4.1')])
def test_selected_glyphs4_beta_receives_components_and_exact_worker_app(tmp_path, identifier, version):
    output, home, app = fixture_install(tmp_path)
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':identifier,'CFBundleShortVersionString':version}))
    result=install(output,home,Path(sys.executable),app)
    assert result['application']==str(app.resolve())
    agent=plistlib.loads(Path(result['launchAgent']).read_bytes())
    arguments=agent['ProgramArguments']
    assert arguments[arguments.index('--glyphs-app')+1]==str(app.resolve())
    assert (home/'Library/Application Support/Glyphs 4/Plugins/Glyphs MCP Bridge.glyphsPlugin').is_dir()


@pytest.mark.parametrize('identifier,version', [('com.GeorgSeifert.Glyphs4Beta','4.2'),('com.GeorgSeifert.GlyphsBeta','4.1'),('com.GeorgSeifert.Glyphs3','3.5'),('com.GeorgSeifert.GlyphsBeta','3.5')])
def test_other_running_copy_blocks_shared_glyphs4_install_but_not_glyphs3(tmp_path,monkeypatch,identifier,version):
    import install_simple_v2 as installer
    app=tmp_path/'Glyphs Other.app'
    (app/'Contents').mkdir(parents=True)
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':identifier,'CFBundleShortVersionString':version}))
    def run(command,**kwargs):
        if command[0]=='/usr/bin/pgrep':return SimpleNamespace(returncode=1,stdout='',stderr='')
        assert command==['/bin/ps','-axo','comm=']
        return SimpleNamespace(returncode=0,stdout=str(app/'Contents/MacOS/Glyphs')+'\n',stderr='')
    monkeypatch.setattr(installer.subprocess,'run',run)
    if version.startswith('4'):
        with pytest.raises(ValueError,match='all copies of Glyphs 4'):
            installer.require_closed_font_processes(tmp_path/'Selected.app')
    else:
        installer.require_closed_font_processes(tmp_path/'Selected.app')


@pytest.mark.parametrize('identifier', ['com.GeorgSeifert.Glyphs3','com.GeorgSeifert.GlyphsBeta'])
def test_glyphs3_cannot_receive_selected_glyphs4_payload(tmp_path, identifier):
    output,home,app=fixture_install(tmp_path)
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':identifier,'CFBundleShortVersionString':'3.5'}))
    with pytest.raises(ValueError,match='Select a Glyphs 4'):
        install(output,home,Path(sys.executable),app)
    assert not home.exists()
