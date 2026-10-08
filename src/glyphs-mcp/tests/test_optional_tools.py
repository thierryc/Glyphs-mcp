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
    path.write_text(json.dumps(dict(schemaVersion=1, tools=tools or {name: dict(status='pending_qualification', reason='Waiting for signing') for name in installer.IDS})))
    return path


def test_pending_assets_are_never_downloaded_or_installed(tmp_path):
    tools = installer.OptionalTools(tmp_path / 'home', catalog(tmp_path))
    assert all(not tools.status(name)['available'] for name in installer.IDS)
    with pytest.raises(ValueError, match='Waiting for signing'): tools.install('diffenator')
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
