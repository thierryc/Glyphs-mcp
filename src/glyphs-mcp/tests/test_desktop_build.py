"""Reject stale or incomplete desktop apps before they become install candidates."""
import json
from pathlib import Path
import plistlib
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
import verify_desktop_app as verifier
import clean_desktop_builds as cleaner
import build_local_app as builder


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    app = tmp_path / 'Glyphs MCP.app'
    info = {'CFBundleIdentifier': 'cx.ap.glyphsMcp', 'CFBundleShortVersionString': '2.0.0',
            'CFBundleVersion': '43', 'CFBundleExecutable': 'Glyphs MCP'}
    for name in ['Contents/MacOS/Glyphs MCP', 'Contents/Resources/Assets.car',
                 'Contents/Frameworks/Sparkle.framework/Sparkle',
                 'Contents/Frameworks/GlyphsMCPInstallerCore.framework/GlyphsMCPInstallerCore']:
        path = app / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture')
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    catalog = tmp_path / 'macos-installer/GlyphsMCPInstaller/Resources/Assets.xcassets'
    for name in ['GlyphsMCPMenu', 'GitHubMark']:
        (catalog / (name + '.imageset')).mkdir(parents=True)
    monkeypatch.setattr(verifier, 'load', lambda root: {'version': '2.0.0', 'installerBuild': 43})
    monkeypatch.setattr(verifier.subprocess, 'check_output', lambda command: json.dumps([
        {'Name': 'GlyphsMCPMenu'}, {'Name': 'GitHubMark'}]).encode())
    return app, tmp_path


def test_rejects_old_asset_catalog_even_when_version_and_executable_match(bundle, monkeypatch):
    app, root = bundle
    monkeypatch.setattr(verifier.subprocess, 'check_output', lambda command: b'[{"Name":"AppIcon"}]')
    with pytest.raises(ValueError, match='Missing compiled assets: GitHubMark, GlyphsMCPMenu'):
        verifier.verify(app, root)


def test_new_source_asset_must_be_in_compiled_catalog(bundle):
    app, root = bundle
    (root / 'macos-installer/GlyphsMCPInstaller/Resources/Assets.xcassets/NewIcon.imageset').mkdir()
    with pytest.raises(ValueError, match='NewIcon'):
        verifier.verify(app, root)


def test_rejects_wrong_build(bundle):
    app, root = bundle
    path = app / 'Contents/Info.plist'
    info = plistlib.loads(path.read_bytes())
    info['CFBundleVersion'] = '42'
    path.write_bytes(plistlib.dumps(info))
    with pytest.raises(ValueError, match='CFBundleVersion'):
        verifier.verify(app, root)


def test_rejects_missing_linked_framework(bundle):
    app, root = bundle
    (app / 'Contents/Frameworks/Sparkle.framework/Sparkle').unlink()
    with pytest.raises(ValueError, match='Missing linked framework: Sparkle'):
        verifier.verify(app, root)


@pytest.mark.parametrize('change', ['source', 'worktree', 'app', 'none'])
def test_receipt_binds_app_to_worktree_and_source(bundle, monkeypatch, change):
    app, root = bundle
    monkeypatch.setattr(verifier, 'source_digest', lambda root: 'source-1')
    receipt = root / 'receipt.json'
    receipt.write_text(json.dumps({'sourceRoot': str(root), 'sourceSHA256': 'source-1',
                                   'bundle': verifier.verify(app, root)}))
    if change == 'source':
        monkeypatch.setattr(verifier, 'source_digest', lambda root: 'source-2')
    elif change == 'worktree':
        data = json.loads(receipt.read_text())
        data['sourceRoot'] = '/another/worktree'
        receipt.write_text(json.dumps(data))
    elif change == 'app':
        (app / 'Contents/MacOS/Glyphs MCP').write_bytes(b'old binary with same version')
    if change == 'none':
        assert verifier.verify_receipt(app, receipt, root)['build'] == '43'
    else:
        with pytest.raises(ValueError, match='receipt'):
            verifier.verify_receipt(app, receipt, root)


def test_cleanup_preserves_source_worktree_even_inside_known_output(tmp_path, monkeypatch):
    monkeypatch.setattr(cleaner.subprocess, 'check_output', lambda command: b'')
    nested = tmp_path / 'build/xcode/source'
    nested.mkdir(parents=True)
    (nested / '.git').write_text('gitdir: elsewhere')
    with pytest.raises(ValueError, match='source worktree'):
        cleaner.clean(tmp_path, apply=True)
    assert (nested / '.git').exists()


def test_cleanup_refuses_tracked_files(tmp_path, monkeypatch):
    monkeypatch.setattr(cleaner.subprocess, 'check_output', lambda command: b'build/xcode/source.swift')
    (tmp_path / 'build/xcode').mkdir(parents=True)
    with pytest.raises(ValueError, match='tracked files'):
        cleaner.clean(tmp_path, apply=True)


def test_cleanup_refuses_redirected_output(tmp_path):
    (tmp_path / 'build').mkdir()
    (tmp_path / 'source').mkdir()
    (tmp_path / 'build/xcode').symlink_to(tmp_path / 'source', target_is_directory=True)
    with pytest.raises(ValueError, match='redirected output'):
        cleaner.clean(tmp_path, apply=True)


def test_cleanup_removes_only_generated_outputs_and_retains_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(cleaner.subprocess, 'check_output', lambda command: b'')
    output = tmp_path / 'build/xcode'
    output.mkdir(parents=True)
    (output / 'Assets.car').write_bytes(b'old assets')
    retained = tmp_path / 'build/source-worktree'
    retained.mkdir()
    (retained / '.git').write_text('gitdir: elsewhere')
    assert cleaner.clean(tmp_path)['bytes'] == 10
    assert output.exists()
    result = cleaner.clean(tmp_path, apply=True)
    assert not output.exists()
    assert (retained / '.git').exists()
    assert Path(result['receipt']).exists()


def test_failed_build_invalidates_old_candidate_and_cleans_temporary_directory(tmp_path, monkeypatch):
    import subprocess
    output = tmp_path / 'dist/local'
    (output / 'Glyphs MCP.app').mkdir(parents=True)
    (output / 'build-receipt.json').write_text('old receipt')
    monkeypatch.setattr(builder, 'ROOT', tmp_path)
    monkeypatch.setattr(builder, 'source_digest', lambda: 'source')
    def run(command, **kwargs):
        if command[0] == 'xcodebuild':
            raise subprocess.CalledProcessError(65, command)
    monkeypatch.setattr(builder.subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        builder.build()
    assert not (output / 'build-receipt.json').exists()
    assert not (output / 'Glyphs MCP.app').exists()
    assert not list((tmp_path / 'build/local-app-runs').iterdir())
