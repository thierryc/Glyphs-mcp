import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('check_skill_catalog', ROOT/'scripts/check_skill_catalog.py')
checker = importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)


def copy_catalog_fixture(destination):
    files = ['catalog-repository/registry.json', 'skills/manifest.json',
             'plugins/glyphs-mcp/.codex-plugin/plugin.json',
             'macos-installer/GlyphsMCPInstaller/Resources/SkillsCatalog/registry.json']
    files += [f'macos-installer/GlyphsMCPInstaller/Resources/{language}.lproj/Localizable.strings'
              for language in ('en', 'fr', 'zh-Hans')]
    for skill in json.loads((ROOT/'skills/manifest.json').read_text())['managedSkills']:
        files += [f'skills/{skill["name"]}/SKILL.md', f'skills/{skill["name"]}/agents/openai.yaml']
    for relative in files:
        target = destination/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)


def test_packaged_catalog_matches_core_skills_and_languages():
    assert checker.check()['bundledSkills'] == 13


def test_path_doctor_download_is_self_contained_and_licensed():
    spec = importlib.util.spec_from_file_location('validate_catalog', ROOT/'catalog-repository/scripts/validate_catalog.py')
    validator = importlib.util.module_from_spec(spec); spec.loader.exec_module(validator)
    folder = ROOT/'skills/glyphs-mcp-path-doctor'
    files = {path.relative_to(folder).as_posix(): path.read_bytes() for path in folder.rglob('*')
             if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'}
    assert validator.validate_files(files, 'glyphs-mcp-path-doctor')['name'] == 'glyphs-mcp-path-doctor'
    assert files['LICENSE'] == (ROOT/'LICENSE').read_bytes()
    assert 'scripts/pen_point_strategy.py' in files


def test_mismatched_snapshot_is_rejected(tmp_path):
    copy_catalog_fixture(tmp_path)
    registry = tmp_path/'catalog-repository/registry.json'
    registry.write_text('{}')
    with pytest.raises(ValueError, match='catalogs differ'):
        checker.check(tmp_path)


def test_incorrect_bundled_license_is_rejected(tmp_path):
    copy_catalog_fixture(tmp_path)
    registry = json.loads((tmp_path/'catalog-repository/registry.json').read_text())
    registry['skills'][0]['license'] = 'MIT'
    for relative in ['catalog-repository/registry.json',
                     'macos-installer/GlyphsMCPInstaller/Resources/SkillsCatalog/registry.json']:
        (tmp_path/relative).write_text(json.dumps(registry))
    with pytest.raises(ValueError, match='bundled license differs'):
        checker.check(tmp_path)


def test_ui_title_drift_is_rejected(tmp_path):
    copy_catalog_fixture(tmp_path)
    ui = tmp_path/'skills/glyphs/agents/openai.yaml'
    ui.write_text(ui.read_text().replace('Glyphs Font Workflows', 'glyphs'))
    with pytest.raises(ValueError, match='Glyphs display title'):
        checker.check(tmp_path)


def test_duplicate_ui_titles_are_rejected(tmp_path):
    copy_catalog_fixture(tmp_path)
    skill = tmp_path/'skills/glyphs-mcp-spacing'
    ui = skill/'agents/openai.yaml'
    ui.write_text(ui.read_text().replace('Glyphs Spacing', 'Glyphs Font Workflows'))
    entry = skill/'SKILL.md'
    entry.write_text(entry.read_text().replace('# Glyphs Spacing', '# Glyphs Font Workflows'))
    with pytest.raises(ValueError, match='Duplicate skill display title'):
        checker.check(tmp_path)
