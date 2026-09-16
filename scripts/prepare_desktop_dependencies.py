#!/usr/bin/env python3
"""Prepare checksum-pinned desktop dependencies for local builds."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
from urllib.request import urlopen
from build_simple_v2 import _identity

ROOT = Path(__file__).resolve().parents[1]


def prepare(archive=None):
    lock = json.loads((ROOT/'third_party/sparkle.json').read_text())
    cache = ROOT/'build/desktop-dependencies'; cache.mkdir(parents=True, exist_ok=True)
    archive = Path(archive) if archive else cache/('Sparkle-'+lock['version']+'.tar.xz')
    if not archive.exists():
        with urlopen(lock['url'], timeout=60) as response:
            data = response.read(32 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != lock['sha256']: raise ValueError('Sparkle archive checksum mismatch')
        archive.write_bytes(data)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['sha256']: raise ValueError('Sparkle archive checksum mismatch')
    marker = cache/'verified-sparkle.json'
    sparkle_ready = False
    if marker.exists() and (cache/'Sparkle.framework').is_dir():
        previous = json.loads(marker.read_text())
        if previous.get('lock') == lock and previous.get('identities') == {name: _identity(cache/name) for name in ('Sparkle.framework', 'bin')}:
            sparkle_ready = True
    if not sparkle_ready:
        with tempfile.TemporaryDirectory(prefix='sparkle-', dir=cache) as temporary:
            with tarfile.open(archive) as stream: stream.extractall(temporary, filter='data')
            for name in ('Sparkle.framework', 'bin', 'LICENSE'):
                target = cache/name
                if target.is_dir(): shutil.rmtree(target)
                elif target.exists(): target.unlink()
                source = Path(temporary)/name
                if source.is_dir(): shutil.copytree(source, target, symlinks=True)
                else: shutil.copy2(source, target)
        marker.write_text(json.dumps({'lock': lock, 'identities': {name: _identity(cache/name) for name in ('Sparkle.framework', 'bin')}}, sort_keys=True, indent=2)+'\n')
    prepare_pierre(cache)
    return cache


def prepare_pierre(cache):
    lock = json.loads((ROOT/'third_party/pierre-diffs-swift.json').read_text())
    patch = ROOT/'third_party/patches/pierre-diffs-swift-local-only.patch'
    patch_sha256 = hashlib.sha256(patch.read_bytes()).hexdigest()
    archive = cache/('PierreDiffsSwift-'+lock['version']+'.tar.gz')
    if not archive.exists():
        with urlopen(lock['url'], timeout=60) as response:
            data = response.read(32 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != lock['sha256']:
            raise ValueError('PierreDiffsSwift archive checksum mismatch')
        archive.write_bytes(data)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['sha256']:
        raise ValueError('PierreDiffsSwift archive checksum mismatch')
    target = cache/'PierreDiffsSwift'
    marker = cache/'verified-pierre-diffs-swift.json'
    if marker.exists() and (target/'Package.swift').is_file():
        previous = json.loads(marker.read_text())
        if (previous.get('lock') == lock and previous.get('patchSHA256') == patch_sha256
                and previous.get('identity') == _identity(target)):
            return
    with tempfile.TemporaryDirectory(prefix='pierre-', dir=cache) as temporary:
        with tarfile.open(archive) as stream:
            stream.extractall(temporary, filter='data')
        roots = [item for item in Path(temporary).iterdir() if item.is_dir()]
        if len(roots) != 1 or not (roots[0]/'Package.swift').is_file():
            raise ValueError('PierreDiffsSwift archive layout is invalid')
        staged = cache/'PierreDiffsSwift.staged'
        if staged.exists(): shutil.rmtree(staged)
        shutil.copytree(roots[0], staged)
        apply_pierre_local_only_patch(staged)
        if target.exists(): shutil.rmtree(target)
        staged.rename(target)
    marker.write_text(json.dumps({'lock': lock, 'patchSHA256': patch_sha256,
                                  'identity': _identity(target)}, sort_keys=True, indent=2)+'\n')


def apply_pierre_local_only_patch(root):
    replacements = {
        'Sources/PierreDiffsSwift/WebView/PierreDiffView.swift': [
            ('    let configuration = WKWebViewConfiguration()\n',
             '    let configuration = WKWebViewConfiguration()\n    configuration.websiteDataStore = .nonPersistent()\n'),
            ('    configuration.preferences.setValue(true, forKey: "developerExtrasEnabled")\n',
             '    configuration.preferences.setValue(false, forKey: "developerExtrasEnabled")\n'),
        ],
        'Sources/PierreDiffsSwift/WebView/DiffHTMLTemplate.swift': [
            ('        <meta charset="UTF-8">\n',
             '        <meta charset="UTF-8">\n        <meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'">\n'),
        ],
        'Sources/PierreDiffsSwift/WebView/DiffWebViewCoordinator.swift': [
            ('extension DiffWebViewCoordinator: WKNavigationDelegate {\n\n',
             'extension DiffWebViewCoordinator: WKNavigationDelegate {\n\n'
             '  public func webView(\n'
             '    _ webView: WKWebView,\n'
             '    decidePolicyFor navigationAction: WKNavigationAction,\n'
             '    decisionHandler: @escaping (WKNavigationActionPolicy) -> Void\n'
             '  ) {\n'
             '    let scheme = navigationAction.request.url?.scheme\n'
             '    decisionHandler(scheme == nil || scheme == "about" ? .allow : .cancel)\n'
             '  }\n\n'),
        ],
    }
    for relative, changes in replacements.items():
        path = root/relative
        text = path.read_text()
        for before, after in changes:
            if text.count(before) != 1:
                raise ValueError(f'PierreDiffsSwift patch context changed: {relative}')
            text = text.replace(before, after)
        path.write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--archive', type=Path)
    args = parser.parse_args(); print(prepare(args.archive))
