"""Optional setup trust boundaries and ownership, without live installation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import sys
import zipfile
import pytest
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import install_optional_tools as installer


def test_plugin_and_cli_trust_require_notarized_install_assessment(tmp_path, monkeypatch):
    from types import SimpleNamespace
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stderr='TeamIdentifier=N9U29A4T8J\n' if '-dv' in command
                               else 'source=Notarized Developer ID\n')
    monkeypatch.setattr(installer.subprocess, 'run', run)
    installer.verify_trust(tmp_path, dict(teamID='N9U29A4T8J', trustSubjects=['.', 'bin/python3']))
    assessments = [command for command in calls if command[0] == '/usr/sbin/spctl']
    assert len(assessments) == 2
    assert all(command[command.index('--type') + 1] == 'install' for command in assessments)
    def unnotarized(command, **kwargs):
        return SimpleNamespace(stderr='TeamIdentifier=N9U29A4T8J\n' if '-dv' in command else 'source=Developer ID\n')
    monkeypatch.setattr(installer.subprocess, 'run', unnotarized)
    with pytest.raises(ValueError, match='notarization ticket'):
        installer.verify_trust(tmp_path, dict(teamID='N9U29A4T8J', trustSubjects=['.']))


def catalog(tmp_path, tools=None):
    path = tmp_path / 'catalog.json'
    entries = tools or {name: dict(status='pending_qualification', reason='Waiting for signing') for name in installer.IDS}
    entries['beztrace-glyphs'].setdefault('engineVersion', '0.2.1')
    path.write_text(json.dumps(dict(schemaVersion=1, tools=entries)))
    return path


def test_pending_assets_are_never_downloaded_or_installed(tmp_path):
    tools = installer.OptionalTools(tmp_path / 'home', catalog(tmp_path))
    assert all(not tools.status(name)['available'] for name in installer.IDS)
    assert all(not tools.status(name)['distributionQualified'] for name in installer.IDS)
    with pytest.raises(ValueError, match='Waiting for signing'): tools.install('diffenator')
    assert not tools.root.exists()


@pytest.mark.parametrize('architecture,os_version,available,reason', [
    ('arm64', '26.6.2', True, None),
    ('x86_64', '26.6.2', False, 'not qualified for x86_64'),
    ('arm64', '14.6.1', False, 'requires macOS 26.0'),
    ('arm64', '', False, 'requires macOS 26.0'),
])
def test_qualification_is_scoped_to_architecture_and_os(tmp_path, monkeypatch, architecture, os_version, available, reason):
    import platform
    monkeypatch.setattr(platform, 'machine', lambda: architecture)
    monkeypatch.setattr(platform, 'mac_ver', lambda: (os_version, (), ''))
    release = dict(minimumMacOS='26.0', archiveURL='https://github.com/example/releases/download/v1/plugin.zip',
                   archiveSHA256='a' * 64)
    tools = installer.OptionalTools(tmp_path / 'home', catalog(tmp_path, {
        'diffenator': dict(status='pending_qualification'),
        'beztrace-glyphs': dict(status='qualified', releases={'arm64': release}),
    }))
    state = tools.status('beztrace-glyphs')
    assert state['available'] is available
    assert state['distributionQualified'] is True
    if reason:
        assert reason in state['reason']
        with pytest.raises(ValueError, match=reason):
            tools.install('beztrace-glyphs')
        assert not tools.root.exists()


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'a/../../outside', 'a\\outside', 'a//b'])
def test_rejects_unsafe_archive_paths(tmp_path, name):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z: z.writestr(name, b'bad')
    with pytest.raises(ValueError): installer.extract(archive, tmp_path / 'stage', {name: hashlib.sha256(b'bad').hexdigest()})


def test_rejects_symlink_and_unknown_inventory(tmp_path):
    archive = tmp_path / 'symlink.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        info = zipfile.ZipInfo('link'); info.create_system = 3; info.external_attr = 0o120777 << 16
        z.writestr(info, 'outside')
    with pytest.raises(ValueError, match='unsupported'): installer.extract(archive, tmp_path / 'stage', {'link': hashlib.sha256(b'outside').hexdigest()})
    archive = tmp_path / 'extra.zip'
    with zipfile.ZipFile(archive, 'w') as z: z.writestr('extra', b'unknown')
    with pytest.raises(ValueError, match='unlisted'): installer.extract(archive, tmp_path / 'stage', {'wanted': '0'*64})


def test_unmanaged_plugin_and_development_links_are_preserved(tmp_path):
    home = tmp_path / 'home'; tools = installer.OptionalTools(home, catalog(tmp_path))
    plugin = tools.target('beztrace-glyphs', {}); (plugin / 'Contents').mkdir(parents=True)
    (plugin / 'Contents/Info.plist').write_bytes(plistlib.dumps(dict(CFBundleIdentifier='dev.beztrace.glyphs', CFBundleVersion='15', CFBundleShortVersionString='0.1.0')))
    assert tools.status('beztrace-glyphs')['state'] == 'unmanaged'
    with pytest.raises(ValueError, match='No ownership receipt'): tools.remove('beztrace-glyphs')
    assert plugin.exists()
    other = home / 'linked-plugin'; plugin.rename(other); plugin.symlink_to(other)
    assert tools.status('beztrace-glyphs')['state'] == 'development_link'


def test_runtime_install_update_remove_and_user_modification(tmp_path, monkeypatch):
    import io
    import platform
    architecture = 'arm64' if platform.machine() == 'arm64' else 'x86_64'
    binary = b'fixture executable'
    payload = {'runtime/runtime.json': json.dumps(dict(schemaVersion=1, architecture=architecture, pythonVersion='3.11.16',
                tool='diffenator2', sourceRevision='cecdab703d462cfea25b748b19ea4813d3f4d680',
                files={'bin/python3': 'sha256:' + hashlib.sha256(binary).hexdigest()})).encode(), 'runtime/bin/python3': binary}
    archive = tmp_path / 'runtime.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for name, value in payload.items(): z.writestr(name, value)
    release = dict(directory='fixture-runtime', version='fixture', archiveURL='https://github.com/example/release/runtime.zip', archiveSize=archive.stat().st_size,
                   archiveSHA256=installer.checksum(archive), payloadRoot='runtime', files={name: hashlib.sha256(value).hexdigest() for name,value in payload.items()})
    tools = installer.OptionalTools(tmp_path / 'home', catalog(tmp_path, dict(diffenator=dict(status='qualified', releases={architecture: release}), **{'beztrace-glyphs': dict(status='pending_qualification')})))
    monkeypatch.setattr(installer.urllib.request, 'urlopen', lambda *a, **kw: io.BytesIO(archive.read_bytes()))
    monkeypatch.setattr(installer, 'verify_trust', lambda *a: None)  # Only unit fixture trust; production has no bypass.
    assert tools.install('diffenator')['installed'] is True
    assert tools.install('diffenator')['installed'] is True
    target = tools.target('diffenator', release)
    (target / 'bin/python3').write_bytes(b'user modified')
    with pytest.raises(ValueError, match='Modified or unowned'): tools.remove('diffenator')
    (target / 'bin/python3').write_bytes(payload['runtime/bin/python3'])
    assert tools.remove('diffenator')['installed'] is False
    assert not target.exists()


@pytest.fixture
def beztrace_upgrade(tmp_path, monkeypatch):
    import io
    import platform
    monkeypatch.setattr(platform, 'machine', lambda: 'arm64')
    monkeypatch.setattr(platform, 'mac_ver', lambda: ('26.6.2', (), ''))
    info = plistlib.dumps(dict(CFBundleIdentifier='dev.beztrace.glyphs',
                              CFBundleShortVersionString='0.2.0', CFBundleVersion='25'))
    archive = tmp_path / 'plugin.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('Beztrace.glyphsPlugin/Contents/Info.plist', info)
    release = dict(version='0.2.0', build=25, directory='beztrace-glyphs-build25',
                   engineConfiguration='manual-selection', payloadRoot='Beztrace.glyphsPlugin',
                   archiveURL='https://github.com/example/releases/plugin.zip',
                   archiveSize=archive.stat().st_size, archiveSHA256=installer.checksum(archive),
                   files={'Beztrace.glyphsPlugin/Contents/Info.plist': hashlib.sha256(info).hexdigest()},
                   teamID='N9U29A4T8J', trustSubjects=['.'])
    tools = installer.OptionalTools(tmp_path / 'home', catalog(tmp_path, {
        'diffenator': dict(status='pending_qualification'),
        'beztrace-glyphs': dict(status='qualified', releases={'arm64': release}),
    }))
    plugin = tools.target('beztrace-glyphs', release)
    (plugin / 'Contents').mkdir(parents=True)
    (plugin / 'Contents/Info.plist').write_bytes(plistlib.dumps(dict(
        CFBundleIdentifier='dev.beztrace.glyphs', CFBundleShortVersionString='0.1.0', CFBundleVersion='16')))
    old_engine = tools.home / 'Library/Application Support/beztrace/engines/0.1.1/bin/beztrace'
    old_engine.parent.mkdir(parents=True); old_engine.write_bytes(b'preserved old engine')
    config = tools.home / 'Library/Application Support/beztrace/engine-settings-v1.json'
    config.write_text(json.dumps(dict(schemaVersion=1, managedEngine=str(old_engine),
                                     userEngine='/explicit/beztrace', extra='preserve')))
    tools.root.mkdir(parents=True)
    tools.receipt_path('beztrace-glyphs').write_text(json.dumps(dict(
        release, version='0.1.0', build=16, target=str(plugin), identity=installer._identity(plugin),
        managedEngine=str(old_engine))))
    engine = tmp_path / 'engine'; (engine / 'bin').mkdir(parents=True)
    (engine / 'bin/beztrace').write_bytes(b'new engine')
    (engine / 'integration-manifest.json').write_text(json.dumps(dict(
        version='0.2.1', files={'bin/beztrace': installer.checksum(engine / 'bin/beztrace')})))
    monkeypatch.setattr(installer.urllib.request, 'urlopen', lambda *a, **kw: io.BytesIO(archive.read_bytes()))
    monkeypatch.setattr(installer, 'verify_trust', lambda *a: None)  # Synthetic fixture only.
    return tools, engine, config, old_engine


@pytest.mark.parametrize('settings_kind', ['regular', 'malformed', 'symlink'])
def test_beztrace_upgrade_uses_new_engine_and_preserves_legacy_choices(beztrace_upgrade, settings_kind):
    tools, engine, config, old_engine = beztrace_upgrade
    if settings_kind == 'malformed':
        config.write_bytes(b'{old invalid settings')
    elif settings_kind == 'symlink':
        linked = config.with_name('user-settings.json')
        config.rename(linked); config.symlink_to(linked)
    before = config.read_bytes()
    assert tools.install('beztrace-glyphs', engine)['version'] == '0.2.0'
    version, target, receipt = tools.engine_paths()
    assert version == '0.2.1'
    assert (target / 'bin/beztrace').read_bytes() == b'new engine'
    assert json.loads(receipt.read_text())['version'] == '0.2.1'
    plugin_receipt = tools.read_receipt('beztrace-glyphs')
    assert plugin_receipt['build'] == 25
    assert plugin_receipt['engineExecutable'] == str(target / 'bin/beztrace')
    assert 'managedEngine' not in plugin_receipt
    assert config.read_bytes() == before
    assert old_engine.read_bytes() == b'preserved old engine'
    # Repeat update, then remove the owned plugin while retaining shared engines/settings.
    tools.install('beztrace-glyphs', engine)
    assert tools.remove('beztrace-glyphs')['installed'] is False
    assert target.exists() and old_engine.exists() and config.read_bytes() == before
    assert config.is_symlink() is (settings_kind == 'symlink')
    allowed = tools.recovery_targets('beztrace-glyphs')
    assert target in allowed and receipt in allowed and old_engine.parent.parent in allowed


@pytest.mark.parametrize('failure', ['wrong_version', 'modified_engine', 'unowned_engine'])
def test_beztrace_upgrade_refuses_invalid_engine_without_replacing_plugin(beztrace_upgrade, failure):
    tools, engine, config, _ = beztrace_upgrade
    before = tools.read_receipt('beztrace-glyphs')
    settings = config.read_bytes()
    if failure == 'wrong_version':
        manifest = engine / 'integration-manifest.json'
        data = json.loads(manifest.read_text()); data['version'] = '0.1.1'
        manifest.write_text(json.dumps(data))
    elif failure == 'modified_engine':
        (engine / 'bin/beztrace').write_bytes(b'modified')
    else:
        _, target, _ = tools.engine_paths()
        target.mkdir(parents=True); (target / 'user-file').write_text('preserve')
    with pytest.raises(ValueError, match='Incompatible bundled engine|inventory differs|Unowned/modified engine'):
        tools.install('beztrace-glyphs', engine)
    assert tools.read_receipt('beztrace-glyphs') == before
    assert installer._identity(tools.target('beztrace-glyphs', before)) == before['identity']
    assert config.read_bytes() == settings


def engine_module():
    path = ROOT / 'integrations/beztrace/engine_settings.py'
    spec = importlib.util.spec_from_file_location('beztrace_engine_settings_test', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_companion_engine_choice_persists_and_overrides_managed_default(tmp_path):
    module = engine_module(); path = module.settings_path(tmp_path); path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(schemaVersion=1, managedEngine='/managed/beztrace', extra='preserve')))
    assert module.selected_engine('/system/beztrace', tmp_path) == '/managed/beztrace'
    executable = tmp_path / 'explicit'; executable.write_text('fixture'); executable.chmod(0o755)
    module.save_user_engine(str(executable), tmp_path)
    reopened = engine_module()
    assert reopened.selected_engine('/system/beztrace', tmp_path) == str(executable)
    assert reopened.load(tmp_path)['extra'] == 'preserve'
    assert reopened.load(tmp_path)['managedEngine'] == '/managed/beztrace'


def test_invalid_engine_settings_do_not_silently_fall_back(tmp_path):
    module = engine_module(); path = module.settings_path(tmp_path); path.parent.mkdir(parents=True)
    path.write_text('{broken')
    with pytest.raises(ValueError): module.selected_engine('/system/beztrace', tmp_path)
