#!/usr/bin/env python3
"""Fetch exactly the locked public runtime inputs; installation itself is offline."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def fetch(url, destination, digest):
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == digest:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix+'.download')
    try:
        with urlopen(url, timeout=60) as response, temporary.open('wb') as output:
            while chunk := response.read(1024*1024): output.write(chunk)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
            raise ValueError('Upstream download identity mismatch: '+destination.name)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def download(architecture, output):
    pin=json.loads((ROOT/'third_party/lean-runtime.json').read_text())['architectures'][architecture]
    fetch(pin['url'], output/('python-'+architecture+'.tar.gz'), pin['sha256'])
    wheels=json.loads((ROOT/f'third_party/lean-runtime-wheels-{architecture}.json').read_text())
    for name,digest in sorted(wheels.items()):
        project,version=name.split('-')[:2]
        with urlopen(f'https://pypi.org/pypi/{project}/{version}/json',timeout=30) as response:
            release=json.load(response)
        artifact=next(item for item in release['urls'] if item['filename']==name)
        if artifact['digests']['sha256'] != digest: raise ValueError('PyPI metadata differs from lock: '+name)
        fetch(artifact['url'],output/('wheels-'+architecture)/name,digest)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--architecture',required=True,choices=['arm64','x86_64'])
    parser.add_argument('--output',type=Path,default=ROOT/'build/runtime-downloads')
    args=parser.parse_args(); download(args.architecture,args.output)
