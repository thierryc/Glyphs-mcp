#!/usr/bin/env python3
"""Prepare a build-16 companion from an exact, disposable build-15 source export.

Uses the upstream package inventory/schema and the reviewed persistent-engine
overlay. Does not modify a checkout, install, sign, launch or publish anything.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import tempfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / 'integrations/beztrace'
BUILD = 16


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def build(source, output):
    provenance = json.loads((OVERLAY / 'SOURCE.json').read_text())
    for name, digest in provenance['packageInputs'].items():
        path = source / name
        if path.is_symlink() or sha(path) != digest:
            raise ValueError('Companion source differs from the reviewed revision: ' + name)
    if output.exists():
        raise ValueError('Use a fresh output directory')
    script = source / 'Companions/Glyphs/scripts/package.py'
    spec = importlib.util.spec_from_file_location('beztrace_package', script)
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    actual_check = subprocess.check_output

    def source_identity(command, **kwargs):
        if command == ['git', 'rev-parse', 'HEAD']:
            return provenance['revision'] + '\n'
        if command == ['git', 'status', '--porcelain', '--untracked-files=normal']:
            return ''
        return actual_check(command, **kwargs)

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='beztrace-companion-', dir=output.parent) as temporary:
        staging = Path(temporary)
        with patch.object(package.subprocess, 'check_output', source_identity):
            manifest = package.build(staging / 'upstream')
        bundle = staging / 'Companions/Glyphs/Beztrace.glyphsPlugin'
        bundle.parent.mkdir(parents=True)
        shutil.copytree(staging / 'upstream/Beztrace.glyphsPlugin', bundle)
        subprocess.run(['/usr/bin/patch', '--batch', '-p1', '-i', str(OVERLAY / 'persistent-engine.patch')],
                       cwd=staging, check=True, capture_output=True)
        resources = bundle / 'Contents/Resources'
        shutil.copy2(OVERLAY / 'engine_settings.py', resources / 'beztrace_companion/engine_settings.py')
        for path in bundle.rglob('*.py'):
            import ast
            ast.parse(path.read_text(), filename=str(path))
        info = bundle / 'Contents/Info.plist'
        metadata = plistlib.loads(info.read_bytes())
        metadata['CFBundleVersion'] = str(BUILD)
        info.write_bytes(plistlib.dumps(metadata))
        overlay_files = {name: sha(OVERLAY / name) for name in ('persistent-engine.patch', 'engine_settings.py')}
        write_json(resources / 'persistent-engine-source.json', dict(
            baseRevision=provenance['revision'], baseFiles=provenance['files'],
            overlayFiles=overlay_files, engineConfiguration='engine-settings-v1',
            companionVersion=metadata['CFBundleShortVersionString'], companionBuild=BUILD,
            nativeVerified=False))
        for document in resources.glob('*.md'):
            document.write_text(document.read_text().replace('build 15', 'build 16'))
        with (resources / 'README.md').open('a') as stream:
            stream.write('\nBuild 16 adds persistent user and managed engine selection through '
                         '`~/Library/Application Support/beztrace/engine-settings-v1.json`. '
                         'Explicit user choices take priority. This local candidate awaits native qualification.\n')
        sbom_path = resources / 'sbom.spdx.json'
        sbom = json.loads(sbom_path.read_text())
        sbom['documentNamespace'] = 'https://beztrace.dev/spdx/glyphs/0.1.0-build16/' + sha(OVERLAY / 'persistent-engine.patch')
        sbom['packages'][0]['versionInfo'] = '0.1.0+build16'
        write_json(sbom_path, sbom)
        output.mkdir()
        shutil.move(str(bundle), output / bundle.name)
    bundle = output / 'Beztrace.glyphsPlugin'
    files = package.inventory(bundle)
    archive = output / 'beztrace-glyphs-0.1.0-build16-macos-universal.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
        for path in sorted(bundle.rglob('*')):
            if not path.is_file(): continue
            entry = zipfile.ZipInfo(path.relative_to(output).as_posix(), (2026, 9, 27, 0, 0, 32))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | (0o755 if path.stat().st_mode & 0o111 else 0o644)) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            stream.writestr(entry, path.read_bytes(), compresslevel=9)
    manifest.update(build=BUILD, sourceTreeDirty=True, payload=files,
                    payloadSha256=hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
    manifest['artifacts'][0].update(path=archive.name, sha256=sha(archive), size=archive.stat().st_size)
    write_json(output / 'companion-manifest.json', manifest)
    (output / 'SHA256SUMS').write_text(''.join(sha(path) + '  ' + path.name + '\n'
                                             for path in (archive, output / 'companion-manifest.json')))
    verifier_spec = importlib.util.spec_from_file_location('beztrace_verify', source / 'Companions/Glyphs/scripts/verify_package.py')
    verifier = importlib.util.module_from_spec(verifier_spec); verifier_spec.loader.exec_module(verifier)
    verifier.verify(output)
    return dict(build=BUILD, sourceRevision=provenance['revision'], archive=str(archive), sha256=sha(archive), nativeVerified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source.resolve(), args.output.absolute()), indent=2))
