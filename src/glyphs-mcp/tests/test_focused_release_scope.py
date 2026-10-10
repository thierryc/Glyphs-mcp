"""Small release profile accepts version-only changes and refuses implementation changes."""
import importlib.util
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from run_focused_release_tests import validate_scope


def test_current_small_release_matches_qualified_swift_and_dependencies():
    result = validate_scope(ROOT, 'v2.0.2-build58')
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
