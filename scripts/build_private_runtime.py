#!/usr/bin/env python3
"""Build a relocatable, locked runtime from verified upstream archives and wheels."""
import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

from build_simple_v2 import _identity

REPO = Path(__file__).resolve().parents[1]


def _wheel_destination(runtime, site, member):
    parts = Path(member).parts
    if not parts or Path(member).is_absolute() or '..' in parts:
        raise ValueError('Unsafe wheel member')
    if not parts[0].endswith('.data'):
        return site.joinpath(*parts)
    if len(parts) < 3:
        raise ValueError('Unsupported wheel data destination: '+member)
    scheme, relative = parts[1], parts[2:]
    if scheme in ('purelib', 'platlib'):
        root = site
    elif scheme == 'data':
        root = runtime
    elif scheme == 'scripts':
        root = runtime/'bin'
    else:
        raise ValueError('Unsupported wheel data destination: '+member)
    return root.joinpath(*relative)


def build(architecture, output, downloads=None):
    lock = json.loads((REPO/'third_party/lean-runtime.json').read_text())
    downloads = Path(downloads or REPO/'build/runtime-downloads')
    archive = downloads/('python-'+architecture+'.tar.gz')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['architectures'][architecture]['sha256']:
        raise ValueError('Python archive identity mismatch')
    wheel_manifest = json.loads((REPO/'third_party'/('lean-runtime-wheels-'+architecture+'.json')).read_text())
    wheels = downloads/('wheels-'+architecture)
    if sorted(p.name for p in wheels.glob('*.whl')) != sorted(wheel_manifest):
        raise ValueError('Locked wheel inventory mismatch')
    for name, digest in wheel_manifest.items():
        if hashlib.sha256((wheels/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Wheel identity mismatch: '+name)
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        temporary = Path(tmp)
        with tarfile.open(archive) as stream:
            stream.extractall(temporary, filter='data')
        runtime = temporary/'python'
        site = runtime/'lib/python3.14/site-packages'
        for name in sorted(wheel_manifest):
            with zipfile.ZipFile(wheels/name) as wheel:
                for info in wheel.infolist():
                    if info.is_dir(): continue
                    destination = _wheel_destination(runtime, site, info.filename)
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    destination.write_bytes(wheel.read(info))
                    destination.chmod(0o755 if info.external_attr >> 16 & 0o111 else 0o644)
        (runtime/'bin/glyphs').symlink_to('../lib/python3.14/site-packages/glyphs_cli/bin/glyphs')
        # Package imports never modify this verified runtime at user launch.
        for cache in runtime.rglob('__pycache__'): shutil.rmtree(cache)
        if output.exists(): shutil.rmtree(output)
        shutil.copytree(runtime, output, symlinks=False)
    return {'architecture':architecture,'pythonVersion':lock['pythonVersion'],
            'identity':_identity(output),'python':'bin/python3','glyphsCLI':'bin/glyphs',
            'wheelHashes':wheel_manifest}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--architecture',required=True,choices=['arm64','x86_64'])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    manifest=build(args.architecture,args.output)
    args.output.with_suffix('.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k!='wheelHashes'}))
