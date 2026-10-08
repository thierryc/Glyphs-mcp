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


def test_kerning_dataset_package_rejects_changed_license_or_pair_payload(tmp_path):
    import shutil
    root=ROOT/'src/protocol/glyphs_mcp_protocol/data/kerning-pairs'
    copied=tmp_path/'kerning-pairs';shutil.copytree(root,copied)
    checker.check_kerning_data(copied)
    (copied/'pairs.json').write_text('{}')
    with pytest.raises(AssertionError):checker.check_kerning_data(copied)
    shutil.copy2(root/'pairs.json',copied/'pairs.json')
    (copied/'LICENSE.md').write_text('missing notice')
    with pytest.raises(AssertionError):checker.check_kerning_data(copied)


@pytest.mark.parametrize('replacement', ['renamed_tool', 'tool_1'])
def test_catalog_check_rejects_renamed_or_duplicate_tools_even_with_seventeen_declarations(tmp_path, replacement):
    server = tmp_path/'src/sidecar/glyphs_mcp_sidecar'
    protocol = tmp_path/'src/protocol/glyphs_mcp_protocol'
    server.mkdir(parents=True); protocol.mkdir(parents=True)
    names = [f'tool_{index}' for index in range(17)]
    (protocol/'models.py').write_text('TOOL_NAMES = '+repr(tuple(names)))
    def declaration(name):
        return '@mcp.tool(name='+repr(name)+')\ndef f(): pass\n'
    (server/'server.py').write_text(''.join(declaration(name) for name in names[:10]))
    (server/'edit_workflow_ui.py').write_text(''.join(declaration(name) for name in names[10:]))
    assert checker.check_tool_catalog(tmp_path) == set(names)
    names[0] = replacement
    (server/'server.py').write_text(''.join(declaration(name) for name in names[:10]))
    with pytest.raises(AssertionError, match='tool contract'):
        checker.check_tool_catalog(tmp_path)


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
