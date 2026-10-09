#!/usr/bin/env python3
"""Fingerprint checkout inputs; generated/ignored outputs are not release source."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(root: Path = ROOT) -> str:
    names = subprocess.check_output([
        'git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'
    ]).decode().split('\0')
    digest = hashlib.sha256()
    for name in sorted(set(names)):
        if not name or name.startswith(('.codex-local/', 'AGENTS', '.agents/', '.codex/')):
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


if __name__ == '__main__':
    print(fingerprint())
