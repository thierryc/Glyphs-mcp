#!/usr/bin/env python3
"""Validate desktop bundle assets and optionally its local build receipt."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess

from desktop_release_identity import load

ROOT = Path(__file__).resolve().parents[1]
BEZTRACE_VERSION = '0.1.1'
BEZTRACE_DIRECTORY = 'Beztrace/beztrace-' + BEZTRACE_VERSION
BEZTRACE_MANIFEST = 'integration-manifest.json'


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
        if not name or not (name.startswith(('macos-installer/', 'scripts/', 'src/', 'third_party/',
                                             'skills/', 'plugins/glyphs-mcp/', 'integrations/')) or name == 'release.json'):
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


def validate_embedded_payload(app):
    """Validate the exact unarchived payload that the desktop app will publish."""
    payload = Path(app) / 'Contents/Resources/Payload'
    if not payload.is_dir():
        raise ValueError('Missing validated desktop installer payload')
    from build_installer_payload import validate_payload
    return validate_payload(payload)


def validate_embedded_beztrace(app):
    root = Path(app) / 'Contents/Resources' / BEZTRACE_DIRECTORY
    manifest_path = root / BEZTRACE_MANIFEST
    checksums_path = root / 'SHA256SUMS'
    if not manifest_path.is_file() or not checksums_path.is_file():
        raise ValueError('Missing embedded beztrace ' + BEZTRACE_VERSION + ' distribution')
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('version') != BEZTRACE_VERSION:
        raise ValueError('Embedded beztrace version mismatch')
    if manifest.get('schemaVersion') != 1 or manifest.get('pathDataVersion') != 2:
        raise ValueError('Embedded beztrace contract version mismatch')
    if set(manifest.get('architectures', [])) != {'arm64', 'x86_64'}:
        raise ValueError('Embedded beztrace architecture metadata is invalid')
    expected = {}
    for line in checksums_path.read_text().splitlines():
        digest, separator, relative = line.partition('  ')
        if (not separator or not re.fullmatch(r'[0-9a-f]{64}', digest)
                or not relative or relative.startswith('/') or '..' in Path(relative).parts
                or relative in expected):
            raise ValueError('Embedded beztrace checksum manifest is invalid')
        expected[relative] = digest
    if any(path.is_symlink() for path in root.rglob('*')):
        raise ValueError('Embedded beztrace distribution contains a symlink')
    files = {
        path.relative_to(root).as_posix()
        for path in root.rglob('*')
        if path.is_file()
    }
    if files != set(expected) | {'SHA256SUMS'}:
        raise ValueError('Embedded beztrace distribution inventory mismatch')
    for relative, digest in expected.items():
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError('Embedded beztrace checksum mismatch: ' + relative)
    if manifest.get('files') != {name: digest for name, digest in expected.items()
                                if name != BEZTRACE_MANIFEST}:
        raise ValueError('Embedded beztrace provenance inventory mismatch')
    upstream_path = root / 'upstream-release-manifest.json'
    upstream = json.loads(upstream_path.read_text())
    provenance = manifest.get('upstreamRelease', {})
    if (upstream.get('version') != BEZTRACE_VERSION
            or upstream.get('sourceRevision') != manifest.get('sourceRevision')
            or upstream.get('minimumMacOS') != manifest.get('minimumMacOS')
            or set(upstream.get('architectures', [])) != {'arm64', 'x86_64'}
            or provenance.get('manifestSHA256') != expected.get('upstream-release-manifest.json')
            or not any(item.get('sha256') == provenance.get('archiveSHA256')
                       and item.get('path') == 'beztrace-' + BEZTRACE_VERSION + '-macos-universal.zip'
                       for item in upstream.get('artifacts', []))):
        raise ValueError('Embedded beztrace upstream provenance mismatch')
    engine = root / 'bin/beztrace'
    if not os.access(engine, os.X_OK):
        raise ValueError('Embedded beztrace engine is not executable')
    architectures = set(subprocess.check_output(['/usr/bin/lipo', '-archs', str(engine)], text=True).split())
    if architectures != {'arm64', 'x86_64'}:
        raise ValueError('Embedded beztrace binary is not universal')
    return {'version': manifest['version'], 'architectures': sorted(architectures),
            'sourceRevision': manifest.get('sourceRevision'),
            'engineSHA256': expected['bin/beztrace']}


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
    validate_embedded_payload(app)
    skills_snapshot = app / 'Contents/Resources/SkillsCatalog/registry.json'
    expected_snapshot = root / 'macos-installer/GlyphsMCPInstaller/Resources/SkillsCatalog/registry.json'
    if not skills_snapshot.is_file() or skills_snapshot.read_bytes() != expected_snapshot.read_bytes():
        raise ValueError('Missing or mismatched offline skills catalog')
    beztrace = validate_embedded_beztrace(app)
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
            'beztrace': beztrace,
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
