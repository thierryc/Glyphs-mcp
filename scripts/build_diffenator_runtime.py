#!/usr/bin/env python3
"""Build a private Diffenator distribution from checksum-locked local inputs.

No downloads, installation, notarization or publication occur here. Supply a
Python standalone archive, an exact wheel inventory, and vendored Unicode data.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

from build_private_runtime import _wheel_destination

REVISION = 'cecdab703d462cfea25b748b19ea4813d3f4d680'
PYTHON_VERSION = '3.11.16'
UNICODE_VERSION = '17.0.0'
ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''): value.update(chunk)
    return value.hexdigest()


def checked(root, item):
    name = item['path']
    if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('Unsafe runtime input path')
    path = root / name
    if path.is_symlink() or digest(path) != item['sha256']:
        raise ValueError('Runtime input checksum differs: ' + name)
    return path


def build(inputs, architecture, output, signing_identity=None):
    configuration = json.loads(inputs.read_text())
    if configuration.get('sourceRevision') != REVISION or configuration.get('pythonVersion') != PYTHON_VERSION:
        raise ValueError('Inputs must use the reviewed Diffenator revision and qualified Python version')
    if configuration.get('unicodeVersion') != UNICODE_VERSION or configuration.get('architecture') != architecture:
        raise ValueError('Unicode version or runtime architecture differs')
    if output.exists(): raise ValueError('Use a new runtime output directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    archive = checked(inputs.parent, configuration['python'])
    unicode_archive = checked(inputs.parent, configuration['unicode'])
    wheel_inputs = configuration['wheels']
    if not isinstance(wheel_inputs, list) or not wheel_inputs:
        raise ValueError('Exact wheel inputs are required')
    wheels = [checked(inputs.parent, item) for item in wheel_inputs]
    with tempfile.TemporaryDirectory(prefix='diffenator-build-', dir=output.parent) as temporary:
        stage = Path(temporary)
        with tarfile.open(archive) as source: source.extractall(stage, filter='data')
        runtime = stage / 'python'
        site = runtime / 'lib/python3.11/site-packages'
        if not (runtime / 'bin/python3').is_file(): raise ValueError('Python archive lacks its expected executable')
        for wheel_path in wheels:
            with zipfile.ZipFile(wheel_path) as wheel:
                for item in wheel.infolist():
                    if item.is_dir(): continue
                    destination = _wheel_destination(runtime, site, item.filename)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(wheel.read(item))
                    destination.chmod(0o755 if item.external_attr >> 16 & 0o111 else 0o644)
        packages = {distribution.metadata['Name'].lower().replace('_', '-'): distribution.version
                    for distribution in importlib.metadata.distributions(path=[str(site)])}
        profile = json.loads((ROOT / 'integrations/diffenator/qualification-arm64.json').read_text())
        if any(packages.get(name) != version for name, version in profile['dependencies'].items()):
            raise ValueError('Resolved dependencies differ from the reviewed compatibility profile')
        if packages.get('diffenator2') is None: raise ValueError('Pinned Diffenator wheel is missing')
        unicode_data = runtime / 'share/diffenator-ucd'; unicode_data.mkdir(parents=True)
        with zipfile.ZipFile(unicode_archive) as source:
            for item in source.infolist():
                if item.is_dir(): continue
                path = Path(item.filename)
                if path.is_absolute() or '..' in path.parts: raise ValueError('Unsafe Unicode archive path')
                target = unicode_data / path; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read(item))
        if not (unicode_data / 'UnicodeData.txt').is_file(): raise ValueError('UnicodeData.txt is missing')
        for cache in runtime.rglob('__pycache__'): shutil.rmtree(cache)
        # Dereference the standalone Python aliases before enforcing a link-free inventory.
        prepared = stage / 'runtime'; shutil.copytree(runtime, prepared, symlinks=False)
        if signing_identity:
            magic = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}
            for path in sorted((p for p in prepared.rglob('*') if p.is_file()), key=lambda p: len(p.parts), reverse=True):
                with path.open('rb') as stream: native = stream.read(4) in magic
                if native:
                    subprocess.run(['/usr/bin/codesign', '--force', '--sign', signing_identity, '--timestamp', '--options', 'runtime', str(path)], check=True)
        manifest = dict(schemaVersion=1, tool='diffenator2', sourceRevision=REVISION, architecture=architecture,
                        pythonVersion=PYTHON_VERSION, unicodeVersion=UNICODE_VERSION, dependencies=packages,
                        files={p.relative_to(prepared).as_posix(): 'sha256:' + digest(p) for p in sorted(prepared.rglob('*')) if p.is_file()},
                        inputLockSHA256=digest(inputs), qualification='candidate; native signed acceptance required')
        (prepared / 'runtime.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
        shutil.move(str(prepared), output)
    zip_path = output.with_suffix('.zip')
    if zip_path.exists(): raise ValueError('Archive destination already exists')
    files = {}
    with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob('*')):
            if not path.is_file(): continue
            name = 'runtime/' + path.relative_to(output).as_posix()
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); entry.create_system = 3
            entry.external_attr = (path.stat().st_mode & 0xffff) << 16; entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, path.read_bytes()); files[name] = digest(path)
    evidence = dict(status='pending_qualification', directory=output.name, architecture=architecture,
                    sourceRevision=REVISION, version='diffenator2-' + REVISION[:12],
                    archiveSize=zip_path.stat().st_size, archiveSHA256=digest(zip_path), payloadRoot='runtime', files=files)
    zip_path.with_suffix('.json').write_text(json.dumps(evidence, sort_keys=True, indent=2) + '\n')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--architecture', choices=('arm64', 'x86_64'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sign-identity')
    args = parser.parse_args()
    result = build(args.inputs.resolve(), args.architecture, args.output.absolute(), args.sign_identity)
    print(json.dumps({key: value for key, value in result.items() if key != 'files'}, indent=2))
