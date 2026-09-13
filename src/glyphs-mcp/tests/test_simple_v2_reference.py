"""Reference comparison behavior and safe, immutable saved/Git source loading."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3] / 'src/companions/reference-inspector'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]/"src/protocol"))
from reference_core.geometry import comparison, path_elements
from reference_core.sources import github_url, resolve_reference, source_hash


BASE = {'width': 500.19, 'anchors': {'top': [200, 700]}, 'outline': [
    [0, [[0, 0]]], [1, [[100, 0]]], [2, [[100, 100], [0, 100], [0, 0]]], [3, []]]}


def test_width_only_changes_do_not_mark_outlines():
    live = deepcopy(BASE)
    live['width'] += 8
    result = comparison(BASE, live)
    assert result['width'] == [500.19, 508.19]
    assert result['outlineChanged'] is False
    assert result['referenceSegments'] == []


def test_contour_and_anchor_differences_keep_reference_geometry():
    live = deepcopy(BASE)
    live['outline'][2][1][0][0] += 20
    live['anchors']['top'][0] += 10
    result = comparison(BASE, live)
    assert result['outlineChanged']
    assert len(result['referenceSegments']) == 1
    assert result['referenceOutline'] == BASE['outline']
    assert result['anchors'] == [{'name': 'top', 'before': [200, 700], 'after': [210, 700]}]
    assert comparison(BASE, deepcopy(BASE))['width'] is None


def test_missing_reference_glyph_can_be_displayed():
    result = comparison({'outline': [], 'anchors': {}, 'width': None}, BASE)
    assert result['width'] == [None, 500.19]
    assert result['currentOutline'] == BASE['outline']


def test_path_capture_checks_bound_before_native_traversal():
    class HugePath:
        def elementCount(self):
            return 8193
        def elementAtIndex_associatedPoints_(self, index):
            raise AssertionError('must not traverse an oversized visible layer')
    with pytest.raises(ValueError, match='display limit'):
        path_elements(HugePath())


@pytest.mark.parametrize('package', [False, True])
def test_saved_reference_is_a_verified_private_copy(tmp_path, package):
    source = tmp_path / ('Font.glyphspackage' if package else 'Font.glyphs')
    if package:
        source.mkdir()
        data = source / 'fontinfo.plist'
    else:
        data = source
    data.write_text('saved source')
    reference = resolve_reference({'kind': 'last_saved'}, str(source), tmp_path/'cache')
    copied = Path(reference['path'])
    assert copied != source
    assert source_hash(copied) == source_hash(source)
    data.write_text('new saved source')
    assert source_hash(copied) != source_hash(source)
    refreshed = resolve_reference({'kind': 'last_saved'}, str(source), tmp_path/'cache')
    assert refreshed['identity'] != reference['identity']


def test_local_git_reference_uses_commit_not_dirty_checkout(tmp_path):
    repo = tmp_path/'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE).decode().strip()
    git('init')
    source = repo/'Font.glyphs'
    source.write_text('committed reference')
    git('add', 'Font.glyphs')
    git('-c', 'user.name=Reference Test', '-c', 'user.email=reference@example.invalid', 'commit', '-m', 'fixture')
    commit = git('rev-parse', 'HEAD')
    source.write_text('unsaved checkout changes')
    reference = resolve_reference({'kind': 'local_git', 'source': str(repo), 'revision': 'HEAD'}, str(source), tmp_path/'cache')
    assert reference['commit'] == commit
    assert Path(reference['path']).read_text() == 'committed reference'
    assert source.read_text() == 'unsaved checkout changes'
    with pytest.raises(ValueError, match='repository-relative'):
        resolve_reference({'kind':'local_git','source':str(repo),'fontPath':'../Font.glyphs'}, str(source), tmp_path/'cache')


@pytest.mark.parametrize('url', ['file:///private/tmp/repo', 'https://evil.invalid/owner/repo',
                                 'https://user:secret@github.com/a/b', 'https://github.com/a/b?token=x'])
def test_github_rejects_nonpublic_or_credential_urls(url):
    with pytest.raises(ValueError, match='public'):
        github_url(url)


def test_github_normalizes_public_repository_url():
    assert github_url('https://github.com/example/fonts') == 'https://github.com/example/fonts.git'


def test_package_rejects_symlinks(tmp_path):
    source = tmp_path/'Font.glyphspackage'
    source.mkdir()
    (source/'fontinfo.plist').symlink_to('/etc/hosts')
    with pytest.raises(ValueError, match='symbolic links'):
        source_hash(source)


def test_open_paths_are_compared_without_filling_them():
    reference={'width':500,'outline':[],'openOutline':[[0,[[0,0]]],[1,[[100,0]]]]}
    current=deepcopy(reference)
    current['openOutline'][1][1][0][1]=30
    result=comparison(reference,current)
    assert result['outlineChanged']
    assert result['referenceSegments']==[[1,[[0,0],[100,0]]]]
    assert result['currentSegments']==[[1,[[0,0],[100,30]]]]
    assert result['referenceOutline']==result['currentOutline']==[]


@pytest.mark.parametrize('distance,changed', [(0.000999, False), (.001, False), (.001001, True), (-.001, False)])
def test_reference_font_unit_tolerance(distance, changed):
    from reference_core.geometry import same_geometry
    assert same_geometry([0, 0], [distance, 0]) is not changed
    before = {'width': 0, 'anchors': {'top': [0, 0]}, 'outline': [[0, [[0, 0]]], [1, [[0, 20]]]]}
    after = deepcopy(before)
    after['width'] = distance
    after['anchors']['top'][0] = distance
    after['outline'][0][1][0][0] = distance
    result = comparison(before, after)
    assert result['outlineChanged'] is changed
    assert bool(result['anchors']) is changed
    assert (result['width'] is not None) is changed


def test_reference_tolerance_does_not_grow_with_coordinates_or_hide_topology():
    from reference_core.geometry import same_geometry
    assert not same_geometry(1e12, 1e12 + .01)
    assert not same_geometry([[0, [[0, 0]]]], [[1, [[0, 0]]]])
    assert not same_geometry([[0, 0]], [[0, 0], [0, 0]])


def test_missing_git_only_blocks_git_references(tmp_path, monkeypatch):
    import reference_core.sources as sources
    monkeypatch.setattr(sources.shutil, 'which', lambda name: None)
    with pytest.raises(ValueError, match='Git references require Git'):
        sources._git('version')
    saved=tmp_path/'saved.glyphs'; saved.write_text('{ familyName = Test; }')
    # Local file resolution never invokes Git.
    result=sources.resolve_reference({'kind':'last_saved'},str(saved),tmp_path/'cache')
    assert Path(result['path']).read_bytes() == saved.read_bytes()


def test_reference_reader_resolves_installed_cli_without_shell_configuration(tmp_path, monkeypatch):
    import reference_core.client as module
    from types import SimpleNamespace
    cli=tmp_path/'private-runtime/bin/glyphs'; cli.parent.mkdir(parents=True);cli.write_text('native')
    receipt=tmp_path/'Library/Application Support/Glyphs MCP/lean-v2/installation.json'
    receipt.parent.mkdir(parents=True);receipt.write_text(json.dumps({'glyphsCLI':str(cli)}))
    monkeypatch.setattr(module.Path,'home',lambda: tmp_path)
    monkeypatch.setattr(module.shutil,'which',lambda name: None)
    commands=[]
    def run(command,**kwargs):
        commands.append(command)
        request=json.loads(Path(command[-1]).read_text())
        Path(request['output']).write_text(json.dumps({'ok':True,'data':{'path':'reference.glyphs','identity':'a','label':'Last Saved','commit':None}}))
        assert kwargs['env']['PYTHONDONTWRITEBYTECODE']=='1'
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module.subprocess,'run',run)
    reader=module.ReferenceReader('/Applications/Selected Glyphs.app')
    reader.read({'source':'/tmp/disposable.glyphs','reference':{'kind':'last_saved'},'epoch':0})
    assert commands[0][0] == str(cli)
    assert commands[0][4] == '/Applications/Selected Glyphs.app'
