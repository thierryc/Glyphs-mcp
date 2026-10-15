#!/usr/bin/env python3
"""Synchronize bundled catalog labels from canonical skill UI metadata."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def ui_metadata(path):
    text = path.read_text()
    result = {}
    for field in ('display_name', 'short_description', 'default_prompt'):
        match = re.search(r'^  ' + field + r': (".*")$', text, re.MULTILINE)
        if not match:
            raise ValueError(f'{path}: missing quoted {field}')
        result[field] = json.loads(match.group(1))
    return result


def check_label(value):
    words = value.split()
    if (not value.startswith('Glyphs ') or len(words) < 2 or value != ' '.join(words)
            or len(value) > 40 or '-' in value or any(ord(c) < 32 for c in value)
            or any(word[0].islower() or word[0].isdigit() for word in words[1:])):
        raise ValueError(f'Use a short Glyphs display title with spaces: {value!r}')


def synchronize(root=ROOT, check=False):
    root = Path(root)
    catalog_path = root / 'catalog-repository/registry.json'
    catalog = json.loads(catalog_path.read_text())
    managed = {entry['name'] for entry in json.loads((root / 'skills/manifest.json').read_text())['managedSkills']}
    titles = set()
    for entry in catalog['skills']:
        if not entry['bundled']:
            if entry.get('displayName'):
                check_label(entry['displayName'])
            continue
        name = entry['name']
        if name not in managed:
            raise ValueError(f'Unknown bundled skill: {name}')
        skill = root / 'skills' / name
        ui = ui_metadata(skill / 'agents/openai.yaml')
        title = ui['display_name']
        check_label(title)
        if title in titles:
            raise ValueError(f'Duplicate skill display title: {title}')
        titles.add(title)
        if not 25 <= len(ui['short_description']) <= 64:
            raise ValueError(f'{name}: short description must be 25–64 characters')
        if '$' + name not in ui['default_prompt']:
            raise ValueError(f'{name}: default prompt must invoke its stable identifier')
        text = (skill / 'SKILL.md').read_text()
        front = text.split('---', 2)[1]
        description = re.search(r'^description: (.+)$', front, re.MULTILINE).group(1)
        if '\n# ' + title + '\n' not in text:
            raise ValueError(f'{name}: skill heading differs from its UI title')
        entry['displayName'] = title
        entry['description'] = description
    data = json.dumps(catalog, indent=2, ensure_ascii=False) + '\n'
    paths = [catalog_path, root / 'macos-installer/GlyphsMCPInstaller/Resources/SkillsCatalog/registry.json']
    for path in paths:
        if check:
            if path.read_text() != data:
                raise ValueError(f'Skill catalog metadata is out of sync: {path}')
        elif path.read_text() != data:
            path.write_text(data)
    return len(managed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(f'{"Verified" if args.check else "Synchronized"} {synchronize(check=args.check)} skill display titles.')
