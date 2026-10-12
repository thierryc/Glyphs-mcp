"""Small release profile accepts version-only changes and refuses implementation changes."""
import importlib.util
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from run_focused_release_tests import validate_scope


def test_focused_gate_accepts_version_only_changes(tmp_path, monkeypatch):
    import run_focused_release_tests as gate
    project = 'macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj'
    info = 'macos-installer/GlyphsMCPInstaller/Info.plist'
    for relative in (project, info):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    def metadata_only(command, **_):
        if 'diff' in command:
            return project + '\n' + info + '\n'
        if 'ls-files' in command:
            return ''
        if 'show' in command:
            relative = command[-1].split(':', 1)[1]
            text = (tmp_path / relative).read_text()
            if relative == project:
                text = gate.re.sub(r'MARKETING_VERSION\s*=\s*[^;]+;', 'MARKETING_VERSION = 2.0.2;', text)
                text = gate.re.sub(r'CURRENT_PROJECT_VERSION\s*=\s*[^;]+;', 'CURRENT_PROJECT_VERSION = 58;', text)
            return text
        return 'fixture-commit\n'
    monkeypatch.setattr(gate.subprocess, 'check_output', metadata_only)
    result = validate_scope(tmp_path, 'v2.0.2-build58')
    assert result['swiftImplementationUnchanged'] and result['dependencyInputsUnchanged']


@pytest.mark.parametrize('path', ['macos-installer/GlyphsMCPInstaller/Core/Changed.swift', 'third_party/changed.lock'])
def test_focused_gate_refuses_unqualified_implementation_changes(monkeypatch, path):
    import run_focused_release_tests as gate
    actual = gate.subprocess.check_output
    def changed(command, **kwargs):
        if 'diff' in command and '--name-only' in command:
            return path + '\n'
        return actual(command, **kwargs)
    monkeypatch.setattr(gate.subprocess, 'check_output', changed)
    with pytest.raises(ValueError, match='Full qualification required'):
        validate_scope(ROOT, 'v2.0.2-build58')
