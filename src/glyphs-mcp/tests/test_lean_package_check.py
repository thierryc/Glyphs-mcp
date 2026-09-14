"""The packaging gate accepts focused references and rejects broken entry links."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('lean_package_check', ROOT/'scripts/check_lean_package.py')
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def test_current_package_passes_with_focused_native_coding_guidance():
    manifest = json.loads((ROOT/'skills/manifest.json').read_text())
    assert checker.check()['skills'] == len(manifest['managedSkills'])


def test_duplicate_manifest_entry_is_rejected(tmp_path, monkeypatch):
    (tmp_path/'skills').mkdir()
    (tmp_path/'skills/manifest.json').write_text(json.dumps({
        'managedSkills': [{'name': 'example'}, {'name': 'example'}],
    }))
    monkeypatch.setattr(checker, 'ROOT', tmp_path)
    with pytest.raises(AssertionError, match='Duplicate managed skill'):
        checker.check()


@pytest.mark.parametrize('target', ['references/missing.md', '../outside.md'])
def test_missing_or_escaping_entry_reference_is_rejected(tmp_path, target):
    root = tmp_path/'skills'
    entry = root/'example'/'SKILL.md'
    entry.parent.mkdir(parents=True)
    if target == '../outside.md':
        # A symlink into a real external file must not pass as bundled evidence.
        outside = tmp_path/'external.md'
        outside.write_text('external')
        (root/'outside.md').symlink_to(outside)
    entry.write_text('---\nname: example\ndescription: Example\nmetadata:\n'
                     '  surface: glyphs-mcp-v2\n---\n[Reference](' + target + ')\n')
    with pytest.raises(AssertionError, match='missing or outside skill tree'):
        checker.check_skill(root, 'example')
