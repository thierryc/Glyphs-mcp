#!/usr/bin/env python3
"""Prepare the checksum-pinned Sparkle framework for local desktop builds."""
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
    if marker.exists() and (cache/'Sparkle.framework').is_dir():
        previous = json.loads(marker.read_text())
        if previous.get('lock') == lock and previous.get('identities') == {name: _identity(cache/name) for name in ('Sparkle.framework', 'bin')}:
            return cache
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
    return cache


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--archive', type=Path)
    args = parser.parse_args(); print(prepare(args.archive))
