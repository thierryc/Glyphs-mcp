#!/usr/bin/env python3
"""Check the offline skills snapshot and contribution bootstrap using stdlib only."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    root = Path(root)
    snapshot = root/'macos-installer/GlyphsMCPInstaller/Resources/SkillsCatalog/registry.json'
    bootstrap = root/'catalog-repository/registry.json'
    if snapshot.read_bytes() != bootstrap.read_bytes():
        raise ValueError('Offline and contribution catalogs differ')
    catalog = json.loads(snapshot.read_text())
    names = {entry['name'] for entry in json.loads((root/'skills/manifest.json').read_text())['managedSkills']}
    if catalog['schemaVersion'] != 1 or {entry['name'] for entry in catalog['skills'] if entry['bundled']} != names:
        raise ValueError('Catalog bundled skills differ from the managed manifest')
    ids = [entry['id'] for entry in catalog['skills']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate catalog IDs')
    bundled_license = json.loads((root/'plugins/glyphs-mcp/.codex-plugin/plugin.json').read_text())['license']
    for entry in catalog['skills']:
        if not re.fullmatch(r'[a-f0-9]{40}', entry['source']['revision']):
            raise ValueError('Catalog revisions must be immutable commits')
        if entry['bundled'] and entry['license'].split(';', 1)[0].strip() != bundled_license:
            raise ValueError('Catalog bundled license differs from the agent plugin: '+entry['name'])
    for language in ('en', 'fr', 'zh-Hans'):
        text = (root/f'macos-installer/GlyphsMCPInstaller/Resources/{language}.lproj/Localizable.strings').read_text()
        for label in ('Companion Plugins', 'AI Agents', 'Skills', 'Import from GitHub…', 'Contribute a Skill', 'Replace with backup'):
            if '"'+label+'" =' not in text:
                raise ValueError('Missing '+language+' label: '+label)
    return {'bundledSkills': len(names), 'catalogSchema': catalog['schemaVersion']}


if __name__ == '__main__':
    print(json.dumps(check(), sort_keys=True))
