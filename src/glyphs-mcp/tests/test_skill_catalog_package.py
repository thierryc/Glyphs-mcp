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
    for relative in files:
        target = destination/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)


def test_packaged_catalog_matches_core_skills_and_languages():
    assert checker.check()['bundledSkills'] == 11


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
