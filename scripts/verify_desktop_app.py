#!/usr/bin/env python3
"""Validate desktop bundle assets and optionally its local build receipt."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess

from desktop_release_identity import load

ROOT = Path(__file__).resolve().parents[1]


def tree_digest(root):
    digest = hashlib.sha256()
    for folder, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(folder) / name
            relative = str(path.relative_to(root))
            if path.is_symlink():
                value = ('link:' + os.readlink(path)).encode()
            elif path.is_file():
                value = hashlib.sha256(path.read_bytes()).digest()
            else:
                continue
            digest.update(relative.encode() + b'\0' + value + b'\0')
        directories.sort()
    return digest.hexdigest()


def source_digest(root=ROOT):
    names = subprocess.check_output(
        ['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard']
    ).decode().split('\0')
    digest = hashlib.sha256()
    for name in sorted(set(names)):
        if not name or not (name.startswith(('macos-installer/', 'scripts/', 'src/', 'third_party/')) or name == 'release.json'):
            continue
        path = root / name
        if path.is_symlink():
            value = ('link:' + os.readlink(path)).encode()
        elif path.is_file():
            value = hashlib.sha256(path.read_bytes()).digest()
        else:
            value = b'missing'
        digest.update(name.encode() + b'\0' + value + b'\0')
    return digest.hexdigest()


def verify(app, root=ROOT):
    app = Path(app)
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    expected = load(root)
    for key, value in {'CFBundleIdentifier': 'cx.ap.glyphsMcp',
                       'CFBundleShortVersionString': expected['version'],
                       'CFBundleVersion': str(expected['installerBuild'])}.items():
        if info.get(key) != value:
            raise ValueError(f'{key}: expected {value!r}, got {info.get(key)!r}')
    if not (app / 'Contents/MacOS' / info['CFBundleExecutable']).is_file():
        raise ValueError('Missing desktop executable')
    for name in ('GlyphsMCPInstallerCore', 'Sparkle'):
        if not (app / 'Contents/Frameworks' / (name + '.framework') / name).is_file():
            raise ValueError(f'Missing linked framework: {name}')
    pierre_lock = json.loads((root / 'third_party/pierre-diffs-swift.json').read_text())
    pierre_bundle = app / 'Contents/Resources/PierreDiffsSwift_PierreDiffsSwift.bundle'
    if not pierre_bundle.is_dir():
        raise ValueError('Missing PierreDiffsSwift package resource bundle')
    pierre_resources = pierre_bundle / 'Contents/Resources/Resources'
    pierre_hashes = {}
    for name, expected_hash in pierre_lock['resources'].items():
        resource = pierre_resources / name
        if not resource.is_file():
            raise ValueError(f'Missing PierreDiffsSwift JavaScript resource: {name}')
        actual_hash = hashlib.sha256(resource.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f'PierreDiffsSwift JavaScript identity mismatch: {name}')
        pierre_hashes[name] = actual_hash
    catalog = root / 'macos-installer/GlyphsMCPInstaller/Resources/Assets.xcassets'
    required = {path.stem for path in catalog.rglob('*.imageset')}
    required.add('GlyphsMCPMenu')
    assets = json.loads(subprocess.check_output(
        ['/usr/bin/assetutil', '--info', str(app / 'Contents/Resources/Assets.car')]
    ))
    missing = required - {item.get('Name') for item in assets}
    if missing:
        raise ValueError('Missing compiled assets: ' + ', '.join(sorted(missing)))
    return {'version': info['CFBundleShortVersionString'], 'build': info['CFBundleVersion'],
            'assets': sorted(required),
            'pierre': {'version': pierre_lock['version'], 'commit': pierre_lock['commit'],
                       'bundleSHA256': tree_digest(pierre_bundle), 'resources': pierre_hashes},
            'appSHA256': tree_digest(app)}


def verify_receipt(app, receipt, root=ROOT):
    value = json.loads(Path(receipt).read_text())
    if value['sourceRoot'] != str(root.resolve()) or value['sourceSHA256'] != source_digest(root):
        raise ValueError('Build receipt belongs to a different worktree or source revision; rebuild the app')
    actual = verify(app, root)
    if actual != value['bundle']:
        raise ValueError('App differs from the verified build receipt; rebuild the app')
    return actual


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    result = verify_receipt(args.app, args.receipt) if args.receipt else verify(args.app)
    print(json.dumps(result, indent=2))
