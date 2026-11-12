"""Resource failures that would otherwise silently fall back to English."""
import copy
import json
from pathlib import Path
import plistlib
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
import check_desktop_localizations as localization


def tables():
    strings = {language: {'Items: %lld — %@': 'Items: %lld — %@'} for language in localization.LOCALES}
    rule = {'files': {'NSStringLocalizedFormatKey': '%#@count@', 'count': {
        'NSStringFormatSpecTypeKey': 'NSStringPluralRuleType',
        'NSStringFormatValueTypeKey': 'lld', 'one': '%lld file', 'other': '%lld files'}}}
    return strings, {language: copy.deepcopy(rule) for language in localization.LOCALES}


def test_all_shipped_languages_have_complete_resources():
    assert localization.check()['locales'] == list(localization.LOCALES)


def test_native_panel_titles_cannot_silently_fall_back_to_english(tmp_path):
    source = tmp_path / localization.RESOURCES / 'en.lproj/Localizable.strings'
    source.parent.mkdir(parents=True)
    source.write_text('"Existing" = "Existing";')
    swift = tmp_path / localization.RESOURCES.parent / 'Sources/Panel.swift'
    swift.parent.mkdir(parents=True)
    swift.write_text('let panel = Self.folderPanel("Open Project Folder")')
    with pytest.raises(ValueError, match='Open Project Folder'):
        localization.check_source_keys(tmp_path)


@pytest.mark.parametrize('content, message', [
    ('"A" = "one"; "A" = "two";', 'duplicate'),
    ('"A" = "";', 'empty'),
    ('"A" = "one"', 'incomplete'),
    ('"A" "one";', 'incomplete'),
    ('"A" = "one"; garbage', 'malformed'),
])
def test_rejects_invalid_source_tables(tmp_path, content, message):
    source = tmp_path / 'Localizable.strings'
    source.write_text(content)
    with pytest.raises(ValueError, match=message):
        localization.read_strings(source)


def test_comments_escapes_and_unicode_are_preserved(tmp_path):
    source = tmp_path / 'Localizable.strings'
    source.write_text('/* comment */\n"A" = "Éléments \\"test\\"\\n下一行"; // trailing\n')
    assert localization.read_strings(source) == {'A': 'Éléments "test"\n下一行'}


def test_format_reordering_and_literal_percent_are_allowed():
    strings, plurals = tables()
    strings['de']['Items: %lld — %@'] = '%2$@ — %1$lld (100%%)'
    localization.validate_tables(strings, plurals)


@pytest.mark.parametrize('translated', ['Items: %@ — %@', 'Items: %lld', 'Items: %lld — %@ — %@', 'Items: %2$lld — %1$@'])
def test_rejects_changed_argument_type_count_or_position(translated):
    strings, plurals = tables()
    strings['de']['Items: %lld — %@'] = translated
    with pytest.raises(ValueError, match='incompatible format'):
        localization.validate_tables(strings, plurals)


def test_rejects_missing_keys_and_plural_forms():
    strings, plurals = tables()
    strings['es'].clear()
    with pytest.raises(ValueError, match='missing'):
        localization.validate_tables(strings, plurals)
    strings, plurals = tables()
    del plurals['pt-BR']['files']['count']['other']
    with pytest.raises(ValueError, match='plural forms'):
        localization.validate_tables(strings, plurals)


def make_bundle(tmp_path):
    app = tmp_path / 'App.app'
    (app / 'Contents').mkdir(parents=True)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleDevelopmentRegion': 'en'}))
    strings, plurals = tables()
    for locale in localization.LOCALES:
        source = tmp_path / localization.RESOURCES / f'{locale}.lproj'
        source.mkdir(parents=True)
        (source / 'Localizable.strings').write_text('\n'.join(
            f'{json.dumps(key)} = {json.dumps(value)};' for key, value in strings[locale].items()))
        (source / 'Localizable.stringsdict').write_bytes(plistlib.dumps(plurals[locale]))
        output = app / f'Contents/Resources/{locale}.lproj'
        output.mkdir(parents=True)
        (output / 'Localizable.strings').write_bytes(plistlib.dumps(strings[locale], fmt=plistlib.FMT_BINARY))
        (output / 'Localizable.stringsdict').write_bytes(plistlib.dumps(plurals[locale]))
    return app


@pytest.mark.skipif(sys.platform != 'darwin', reason='Built strings are decoded with Apple plutil')
def test_verifies_compiled_tables_and_rejects_stale_translation(tmp_path):
    app = make_bundle(tmp_path)
    assert localization.verify_bundle(app, tmp_path)['keys'] == 1
    path = app / 'Contents/Resources/fr.lproj/Localizable.strings'
    path.write_bytes(plistlib.dumps({'Items: %lld — %@': 'Stale %lld %@'}))
    with pytest.raises(ValueError, match='differ from source'):
        localization.verify_bundle(app, tmp_path)


def test_rejects_missing_development_language(tmp_path):
    app = make_bundle(tmp_path)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({}))
    with pytest.raises(ValueError, match='development language'):
        localization.verify_bundle(app, tmp_path)


def test_rejects_duplicate_plural_keys(tmp_path):
    path = tmp_path / 'Localizable.stringsdict'
    path.write_text('<plist><dict><key>count</key><dict/><key>count</key><dict/></dict></plist>')
    with pytest.raises(ValueError, match='duplicate plural key'):
        localization.read_plurals(path)


def test_compiler_extraction_checks_actual_numeric_interpolation(tmp_path):
    source = tmp_path / localization.RESOURCES / 'en.lproj/Localizable.strings'
    source.parent.mkdir(parents=True)
    source.write_text('"Items: %@" = "Items: %@";')
    extraction = tmp_path / 'Objects/View.stringsdata'
    extraction.parent.mkdir()
    extraction.write_text(json.dumps({'source': '/app/GlyphsMCPInstaller/Sources/View.swift',
        'tables': {'Localizable': [{'key': 'Items: %lld'}]}}))
    with pytest.raises(ValueError, match='Items: %lld'):
        localization.check_extracted(extraction.parent, tmp_path)
