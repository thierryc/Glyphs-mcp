#!/usr/bin/env python3
"""Validate the native app's translation tables, plural rules and format arguments."""
import argparse
import json
from pathlib import Path
import plistlib
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ('en', 'fr', 'zh-Hans', 'de', 'es', 'pt-BR')
RESOURCES = Path('macos-installer/GlyphsMCPInstaller/Resources')
TOKEN = re.compile(r'\s+|/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|[=;]', re.S)
FORMAT = re.compile(r'%(?:(\d+)\$)?[-+ #0]*(?:\d+)?(?:\.\d+)?(hh|ll|[hlLzjt])?([@diuoxXfFeEgGaAcCsSp])')


def read_strings(path):
    """Parse source text without silently accepting duplicate keys like plutil does."""
    text = Path(path).read_text(encoding='utf-8-sig')
    tokens, end = [], 0
    for match in TOKEN.finditer(text):
        if match.start() != end:
            raise ValueError(f'{path}: malformed strings near {text[end:end+50]!r}')
        token = match.group()
        end = match.end()
        if not token.isspace() and not token.startswith(('/*', '//')):
            tokens.append(token)
    if end != len(text):
        raise ValueError(f'{path}: malformed trailing content')
    if len(tokens) % 4:
        raise ValueError(f'{path}: incomplete strings entry')
    result = {}
    for i in range(0, len(tokens), 4):
        key, equals, value, semicolon = tokens[i:i+4]
        if equals != '=' or semicolon != ';' or not key.startswith('"') or not value.startswith('"'):
            raise ValueError(f'{path}: malformed entry {tokens[i:i+4]}')
        key, value = json.loads(key), json.loads(value)
        if key in result:
            raise ValueError(f'{path}: duplicate key {key!r}')
        if not value.strip():
            raise ValueError(f'{path}: empty translation for {key!r}')
        result[key] = value
    return result


def arguments(value):
    """Compare argument positions/types; %% consumes no argument."""
    result, next_position, position = {}, 1, 0
    while position < len(value):
        if value.startswith('%%', position):
            position += 2
            continue
        if value[position] != '%':
            position += 1
            continue
        match = FORMAT.match(value, position)
        if not match:
            # A percentage in ordinary prose is not a printf argument.
            position += 1
            continue
        explicit, length, kind = match.groups()
        index = int(explicit) if explicit else next_position
        if not explicit:
            next_position += 1
        signature = (length or '') + ('d' if kind == 'i' else kind)
        if index in result and result[index] != signature:
            raise ValueError(f'Conflicting format types at argument {index}: {value!r}')
        result[index] = signature
        position = match.end()
    return result


def read_plurals(path):
    data = Path(path).read_bytes()
    if not data.startswith(b'bplist'):
        for dictionary in ET.fromstring(data).iter('dict'):
            keys = [key.text for key in dictionary.findall('key')]
            if len(keys) != len(set(keys)):
                raise ValueError(f'{path}: duplicate plural key')
    return plistlib.loads(data)


def validate_tables(tables, plurals):
    english = tables['en']
    for language in LOCALES:
        table = tables[language]
        if table.keys() != english.keys():
            raise ValueError(f'{language}: missing {sorted(english.keys()-table.keys())}; extra {sorted(table.keys()-english.keys())}')
        for key, value in table.items():
            if not value.strip() or arguments(value) != arguments(english[key]):
                raise ValueError(f'{language}: empty or incompatible format for {key!r}: {value!r}')
        rules = plurals[language]
        if rules.keys() != plurals['en'].keys():
            raise ValueError(f'{language}: plural keys differ from English')
        for key, entry in rules.items():
            reference = plurals['en'][key]
            if entry.keys() != reference.keys() or entry.get('NSStringLocalizedFormatKey') != reference['NSStringLocalizedFormatKey']:
                raise ValueError(f'{language}: malformed plural entry {key!r}')
            for variable, rule in entry.items():
                if variable == 'NSStringLocalizedFormatKey':
                    continue
                if rule.get('NSStringFormatSpecTypeKey') != 'NSStringPluralRuleType' or rule.get('NSStringFormatValueTypeKey') != 'lld':
                    raise ValueError(f'{language}: invalid plural type for {key!r}')
                required = {'other'} if language == 'zh-Hans' else {'one', 'other'}
                if not required.issubset(rule):
                    raise ValueError(f'{language}: missing plural forms for {key!r}')
                for category, value in rule.items():
                    if category.startswith('NSString'):
                        continue
                    if category not in {'zero', 'one', 'two', 'few', 'many', 'other'}:
                        raise ValueError(f'{language}: invalid plural category {category!r}')
                    if not value.strip() or arguments(value) != {1: 'lld'}:
                        raise ValueError(f'{language}: invalid plural format for {key!r}/{category}')
    return {'locales': list(LOCALES), 'keys': len(english), 'pluralKeys': len(plurals['en'])}


def check(root=ROOT):
    resources = Path(root) / RESOURCES
    check_source_keys(root)
    return validate_tables(
        {locale: read_strings(resources / f'{locale}.lproj/Localizable.strings') for locale in LOCALES},
        {locale: read_plurals(resources / f'{locale}.lproj/Localizable.stringsdict') for locale in LOCALES},
    )


def check_source_keys(root=ROOT):
    """Cover explicit localization helpers and dynamic native panel titles."""
    english = read_strings(Path(root) / RESOURCES / 'en.lproj/Localizable.strings')
    calls = re.compile(r'(?:AppLocalization\.(?:text|format|count)|folderPanel|NSLocalizedString)\(\s*("(?:\\.|[^"\\])*")')
    missing = {}
    for folder in ('Sources', 'Core'):
        for path in (Path(root) / RESOURCES.parent / folder).rglob('*.swift'):
            for match in calls.finditer(path.read_text()):
                try:
                    key = json.loads(match[1])
                except ValueError:
                    continue  # Swift interpolation is checked by compiler extraction.
                if key and key not in english:
                    missing.setdefault(key, []).append(path.name)
    if missing:
        raise ValueError('Missing explicit localization keys: ' + json.dumps(missing, ensure_ascii=False))


def check_extracted(directory, root=ROOT):
    """Check compiler-emitted SwiftUI keys, including the actual interpolation types."""
    english = read_strings(Path(root) / RESOURCES / 'en.lproj/Localizable.strings')
    missing = {}
    for path in Path(directory).rglob('*.stringsdata'):
        data = json.loads(path.read_text())
        source = data.get('source', '')
        if '/GlyphsMCPInstaller/Sources/' not in source and '/GlyphsMCPInstaller/Core/' not in source:
            continue
        for entry in data.get('tables', {}).get('Localizable', []):
            key = entry['key']
            if key and key not in english:
                missing.setdefault(key, []).append(Path(source).name)
    if missing:
        raise ValueError('Missing compiler-extracted keys: ' + json.dumps(missing, ensure_ascii=False))


def verify_bundle(app, root=ROOT):
    app = Path(app)
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    if info.get('CFBundleDevelopmentRegion') != 'en':
        raise ValueError('Desktop development language must be English')
    tables, plurals = {}, {}
    for locale in LOCALES:
        folder = app / f'Contents/Resources/{locale}.lproj'
        # Xcode may compile .strings into binary plists or UTF-16 text.
        tables[locale] = plistlib.loads(subprocess.check_output(
            ['/usr/bin/plutil', '-convert', 'xml1', '-o', '-', str(folder / 'Localizable.strings')]))
        plurals[locale] = read_plurals(folder / 'Localizable.stringsdict')
        source = Path(root) / RESOURCES / f'{locale}.lproj'
        if tables[locale] != read_strings(source / 'Localizable.strings') or plurals[locale] != read_plurals(source / 'Localizable.stringsdict'):
            raise ValueError(f'{locale}: built translations differ from source')
    return validate_tables(tables, plurals)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path)
    parser.add_argument('--extracted', type=Path, help='Xcode intermediates with emitted .stringsdata')
    args = parser.parse_args()
    if args.extracted:
        check_extracted(args.extracted)
    print(json.dumps(verify_bundle(args.app) if args.app else check(), ensure_ascii=False))
