"""Local evaluation install preserves unrelated plugins and replacement backups."""
import json
import plistlib
import sys
from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO/'scripts'))
from build_simple_v2 import build
from install_simple_v2 import install, service_controller as load_service_controller


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
