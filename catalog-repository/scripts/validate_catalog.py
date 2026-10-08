#!/usr/bin/env python3
"""Validate catalog metadata and packages without executing contributed code."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen
import zipfile

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


def relative(value):
    if (not value or value.startswith('/') or '\\' in value or
            any(ord(c) < 32 for c in value) or
            any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('Unsafe relative path: ' + value)
    return value


def metadata(data):
    if len(data) > 1_000_000:
        raise ValueError('SKILL.md is too large')
    text = data.decode('utf-8').replace('\r\n', '\n')
    lines = text.splitlines()
    if not lines or lines[0] != '---' or '---' not in lines[1:]:
        raise ValueError('Missing YAML frontmatter')
    front = '\n'.join(lines[1:lines.index('---', 1)])
    if any(isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken, yaml.tokens.TagToken)) for token in yaml.scan(front)):
        raise ValueError('YAML aliases and tags are unsupported')
    node = yaml.compose(front)
    if not isinstance(node, yaml.MappingNode):
        raise ValueError('Metadata must be a mapping')
    keys = [key.value for key, _ in node.value]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate metadata keys')
    values = yaml.safe_load(front)
    name = values.get('name')
    description = values.get('description')
    if not isinstance(name, str) or len(name) > 64 or not NAME.fullmatch(name):
        raise ValueError('Invalid skill name')
    if not isinstance(description, str) or not 1 <= len(description) <= 1024:
        raise ValueError('Invalid skill description')
    return values


def validate_files(files, expected=None):
    if 'SKILL.md' not in files:
        raise ValueError('Missing SKILL.md')
    names = [relative(name) for name in files]
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError('Duplicate package names')
    values = metadata(files['SKILL.md'])
    if expected and values['name'] != expected:
        raise ValueError('Catalog and frontmatter names differ')
    for name, content in files.items():
        if not name.endswith('.md'):
            continue
        for link in re.findall(r'\]\(([^\s)]+)(?:\s+[^)]*)?\)', content.decode('utf-8')):
            if link.startswith('#') or urlsplit(link).scheme:
                continue
            path = unquote(link.split('#')[0])
            parts = list(PurePosixPath(name).parent.parts)
            for part in path.split('/'):
                if part == '.':
                    continue
                if part == '..':
                    if not parts:
                        raise ValueError('Reference leaves skill folder')
                    parts.pop()
                else:
                    parts.append(part)
            path = relative('/'.join(parts))
            if path not in files:
                raise ValueError('Missing reference: ' + path)
    return values


def archive_files(data, directory):
    if len(data) > 20 * 1024 * 1024:
        raise ValueError('Archive is too large')
    with zipfile.ZipFile(io.BytesIO(data)) as stream:
        entries = stream.infolist()
        if not 1 <= len(entries) <= 10_000 or sum(item.file_size for item in entries) > 64 * 1024 * 1024:
            raise ValueError('Expanded archive exceeds limits')
        names = set()
        roots = set()
        for item in entries:
            name = relative(item.filename.rstrip('/'))
            if name.casefold() in names or item.flag_bits & 1:
                raise ValueError('Duplicate or encrypted ZIP entry')
            names.add(name.casefold()); roots.add(name.split('/')[0])
            mode = stat.S_IFMT(item.external_attr >> 16)
            if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError('Links/special ZIP files are unsupported')
        if len(roots) != 1:
            raise ValueError('Archive needs one top-level folder')
        base = roots.pop() + '/'
        if directory != '.':
            base += relative(directory) + '/'
        return {item.filename[len(base):]: stream.read(item) for item in entries
                if item.filename.startswith(base) and not item.is_dir()}


def download(url):
    request = Request(url, headers={'User-Agent': 'Glyphs-MCP-Catalog-Validation'})
    with urlopen(request, timeout=30) as response:
        if urlsplit(response.url).hostname != urlsplit(url).hostname:
            raise ValueError('Unexpected download redirect')
        return response.read(20 * 1024 * 1024 + 1)


def validate(root=ROOT, fetch=False):
    root = Path(root)
    raw = (root/'registry.json').read_bytes()
    if len(raw) > 512_000:
        raise ValueError('Registry too large')
    registry = json.loads(raw)
    jsonschema.Draft202012Validator(json.loads((root/'registry-v1.schema.json').read_text())).validate(registry)
    ids, names = set(), set()
    for entry in registry['skills']:
        if entry['id'] in ids or entry['name'] in names:
            raise ValueError('Duplicate skill ID/name')
        ids.add(entry['id']); names.add(entry['name'])
        source = entry['source']
        if source['directory'] != '.':
            relative(source['directory'])
        if entry['bundled']:
            if (entry['id'] != 'builtin:'+entry['name'] or source['repository'] != 'https://github.com/thierryc/Glyphs-mcp'
                    or source['directory'] != 'skills/'+entry['name']):
                raise ValueError('Invalid canonical bundled reference')
        elif fetch:
            url = source['repository'].replace('https://github.com/', 'https://codeload.github.com/')+'/zip/'+source['revision']
            data = download(url)
            if hashlib.sha256(data).hexdigest() != source['archiveSHA256']:
                raise ValueError('Archive checksum mismatch')
            validate_files(archive_files(data, source['directory']), entry['name'])
    for directory in [root/'skills', root/'template']:
        if not directory.exists():
            continue
        for path in directory.rglob('SKILL.md'):
            folder = path.parent
            files = {}
            for resource in folder.rglob('*'):
                if resource.is_symlink():
                    raise ValueError('Local packages cannot contain symbolic links')
                if resource.is_file():
                    files[resource.relative_to(folder).as_posix()] = resource.read_bytes()
            value = validate_files(files)
            if value['name'] != folder.name:
                raise ValueError('Folder and metadata names differ')
    return len(registry['skills'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-sources', action='store_true')
    args = parser.parse_args()
    print(f'Validated {validate(fetch=args.fetch_sources)} skills. No contributed programs were executed.')
