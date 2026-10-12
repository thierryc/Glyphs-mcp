"""Default-module detection without modifying Glyphs preferences or fonts."""

import importlib.util
import json
import plistlib
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO = Path(__file__).resolve().parents[3]
HELPER = REPO / 'src/protocol/glyphs_mcp_protocol/python_runtime.py'
spec = importlib.util.spec_from_file_location('glyphs_python_detection', HELPER)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def fixture(tmp_path, identifier='com.GeorgSeifert.Glyphs4'):
    app = tmp_path / 'Glyphs 4.app'
    (app / 'Contents').mkdir(parents=True)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': identifier, 'CFBundleShortVersionString': '4.1.1'}))
    versions = tmp_path / 'home/Library/Application Support/Glyphs 4/Repositories/Python/Python.framework/Versions'
    python = versions / '3.14/Python'
    python.parent.mkdir(parents=True)
    python.write_bytes(b'framework fixture')
    (versions / 'Current').symlink_to('3.14')
    return app, tmp_path / 'home', python


@pytest.mark.parametrize('identifier', ['com.GeorgSeifert.Glyphs4', 'com.GeorgSeifert.Glyphs4Beta', 'com.GeorgSeifert.GlyphsBeta'])
def test_installed_default_without_saved_preference(tmp_path, monkeypatch, identifier):
    app, home, python = fixture(tmp_path, identifier)
    calls = []
    def defaults(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout='', stderr='The domain/default pair does not exist')
    monkeypatch.setattr(runtime.subprocess, 'run', defaults)
    assert runtime.python_arguments(app, home=home) == ['--python', str(python)]
    assert calls == [['/usr/bin/defaults', 'read', identifier, 'GSPythonFrameworkPath']]


@pytest.mark.parametrize('selection', ['/custom/Python.framework/Versions/3.14', '/missing/framework', '~unknown-glyphs-account/Python', ''])
def test_explicit_selection_is_never_overridden(tmp_path, monkeypatch, selection):
    app, home, _ = fixture(tmp_path)
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k:
        SimpleNamespace(returncode=0, stdout=selection, stderr=''))
    assert runtime.python_arguments(app, home=home) == []


def test_failed_preference_read_does_not_select_another_python(tmp_path, monkeypatch):
    app, home, _ = fixture(tmp_path)
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k:
        SimpleNamespace(returncode=1, stdout='', stderr='Permission denied'))
    with pytest.raises(ValueError, match='Could not read'):
        runtime.python_arguments(app, home=home)


def test_other_application_does_not_inherit_glyphs4_python(tmp_path, monkeypatch):
    app, home, _ = fixture(tmp_path, 'com.GeorgSeifert.Glyphs3')
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k: pytest.fail('wrong preference domain'))
    assert runtime.python_arguments(app, home=home) == []


def test_missing_default_keeps_cli_setup_diagnostic(tmp_path, monkeypatch):
    app, home, python = fixture(tmp_path)
    python.unlink()
    is_file = Path.is_file
    monkeypatch.setattr(Path, 'is_file', lambda path: is_file(path) if path.is_relative_to(tmp_path) else False)
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k:
        SimpleNamespace(returncode=1, stdout='', stderr='The domain/default pair does not exist'))
    assert runtime.python_arguments(app, home=home) == []


def test_preflight_uses_shipped_default_resolver_without_writing_payload(tmp_path, monkeypatch):
    sys.path.insert(0, str(REPO / 'scripts'))
    import install_simple_v2 as installer
    from build_simple_v2 import _identity
    app, home, python = fixture(tmp_path)
    output = tmp_path / 'payload'
    helper = output / 'sidecar/glyphs_mcp_protocol/python_runtime.py'
    helper.parent.mkdir(parents=True)
    shutil.copy2(HELPER, helper)
    (output / 'manifest.json').write_text(json.dumps({'runtimes': {
        installer.platform.machine(): {'path': 'runtime', 'glyphsCLI': 'bin/glyphs'}
    }}))
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        if command[0] == '/usr/bin/defaults':
            return SimpleNamespace(returncode=1, stdout='', stderr='The domain/default pair does not exist')
        assert command[command.index('--python') + 1] == str(python)
        assert kwargs['env']['PYTHONDONTWRITEBYTECODE'] == '1'
        return SimpleNamespace(returncode=0, stdout='GLYPHS_MCP_NATIVE_READY:3.14.6\n', stderr='')
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))
    monkeypatch.setattr(installer.subprocess, 'run', run)
    monkeypatch.setattr(sys, 'dont_write_bytecode', False)
    before = _identity(output)
    assert installer.preflight(output, app) == '3.14.6'
    assert _identity(output) == before
    assert len(commands) == 2


def test_selection_diagnostics_distinguish_installed_module_from_missing_preference(tmp_path, monkeypatch):
    app, home, python = fixture(tmp_path)
    events = []
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *a, **k:
        SimpleNamespace(returncode=1, stdout='', stderr='The domain/default pair does not exist'))
    assert runtime.python_arguments(app, home=home, diagnostic=events.append) == ['--python', str(python)]
    preference = next(row for row in events if row['event'] == 'python.preference')
    assert preference['domain'] == 'com.GeorgSeifert.Glyphs4' and preference['state'] == 'absent'
    candidates = next(row for row in events if row['event'] == 'python.default-candidates')['candidates']
    assert candidates[0]['exists'] and candidates[0]['resolvedPath'] == str(python)
    assert events[-1]['source'] == 'default-module'


@pytest.mark.parametrize('failure', ['unconfigured', 'timeout'])
def test_failed_preflight_retains_correlated_native_evidence(tmp_path, monkeypatch, capsys, failure):
    sys.path.insert(0, str(REPO / 'scripts'))
    import install_simple_v2 as installer
    app, home, _ = fixture(tmp_path)
    build = tmp_path/'payload'
    helper = build/'sidecar/glyphs_mcp_protocol/python_runtime.py'
    helper.parent.mkdir(parents=True)
    shutil.copy2(HELPER, helper)
    (build/'manifest.json').write_text(json.dumps({'runtimes': {
        installer.platform.machine(): {'path':'runtime','glyphsCLI':'bin/glyphs','pythonVersion':'3.14.7','glyphsCLIVersion':'0.6.1'}
    }}))
    def run(command, **kwargs):
        if command[0] == '/usr/bin/defaults':
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        if failure == 'timeout':
            raise installer.subprocess.TimeoutExpired(command,45,output=b'initial native output',stderr=b'native stalled')
        return SimpleNamespace(returncode=1, stdout='native startup output', stderr='No Python framework path configured.')
    monkeypatch.setattr(installer.subprocess,'run',run)
    with pytest.raises((ValueError,installer.subprocess.TimeoutExpired)):
        installer.preflight(build,app,installer.SetupDiagnostics('check-123'))
    rows = [json.loads(line.removeprefix('GLYPHS_MCP_SETUP:')) for line in capsys.readouterr().err.splitlines()]
    assert {row['checkId'] for row in rows} == {'check-123'}
    assert all(row['schemaVersion'] == 1 and 'elapsedSeconds' in row for row in rows)
    assert next(row for row in rows if row['event']=='python.app')['bundleIdentifier']=='com.GeorgSeifert.Glyphs4'
    assert next(row for row in rows if row['event']=='python.preference')['state']=='empty'
    result=next(row for row in rows if row['event'] in {'python.native-result','python.native-timeout'})
    assert 'native' in result['stdout']
    assert rows[-1]['reason'] == ('native-timeout' if failure=='timeout' else 'framework-setting-missing')


def test_diagnostics_bound_output_and_redact_credentials_and_account_paths(capsys):
    sys.path.insert(0,str(REPO/'scripts'))
    import install_simple_v2 as installer
    installer.SetupDiagnostics('check-redaction').emit('test', stderr='/Users/another/Python Authorization: Bearer sensitive token=private "password":"hidden" '+('x'*10000))
    text=capsys.readouterr().err
    assert 'sensitive' not in text and 'private' not in text and 'hidden' not in text and '/Users/another' not in text
    row=json.loads(text.removeprefix('GLYPHS_MCP_SETUP:'))
    assert row['stderr'].startswith('~/Python') and len(row['stderr'])<=8192


def test_generic_glyphs3_beta_cannot_use_glyphs4_default_module(tmp_path, monkeypatch):
    app, home, _ = fixture(tmp_path, 'com.GeorgSeifert.GlyphsBeta')
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier':'com.GeorgSeifert.GlyphsBeta','CFBundleShortVersionString':'3.5'}))
    monkeypatch.setattr(runtime.subprocess,'run',lambda *a,**k:pytest.fail('Glyphs 3 must not inherit the Glyphs 4 default'))
    assert runtime.python_arguments(app,home=home)==[]
