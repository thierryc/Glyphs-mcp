#!/usr/bin/env python3
"""Remove known generated desktop outputs, never source worktrees or dependencies."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
# Deliberately explicit: build/ also contains source worktrees and review evidence.
OUTPUTS = (
    'build/xcode', 'build/xcode-release', 'build/desktop-deriveddata',
    'build/desktop-timeout-tests', 'build/popover-version-clean',
    'build/popover-version/Glyphs MCP.app',
    'build/update-trial/Glyphs MCP.app', 'build/update-trial/older.zip',
    'build/final-payload-a', 'build/final-payload-b', 'build/installer-payload',
    'build/notarized-payload', 'build/payload-check-a', 'build/payload-check-b',
    'build/signed-final-check', 'build/signed-payload',
    'build/signing-deterministic-a', 'build/signing-deterministic-b',
    'dist/installer-app/GlyphsMCPInstaller.app',
    'dist/installer-app/GlyphsMCPInstaller.xcarchive',
    'dist/installer-app/GlyphsMCPInstaller.zip',
    'dist/installer-app/GlyphsMCPInstaller-SIGNED-UNNOTARIZED.zip',
    'dist/installer-app/Glyphs MCP.app',
    'dist/Glyphs-MCP-2.0.0.dmg',
)


def inspect(root, relative):
    if relative not in OUTPUTS:
        raise ValueError(f'Not a recognized generated output: {relative}')
    path = root / relative
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or path.resolve() != root.resolve() / relative:
        raise ValueError(f'Refusing redirected output: {path}')
    tracked = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--', relative])
    if tracked:
        raise ValueError(f'Refusing output containing tracked files: {path}')
    size = path.lstat().st_size if path.is_file() else 0
    for folder, directories, files in os.walk(path, followlinks=False):
        if '.git' in directories + files:
            raise ValueError(f'Refusing output containing a source worktree: {folder}')
        for name in files:
            size += (Path(folder) / name).lstat().st_size
    return {'path': str(path), 'bytes': size}


def clean(root, apply=False):
    root = root.resolve()
    records = [record for name in OUTPUTS if (record := inspect(root, name))]
    report = {'root': str(root), 'applied': apply, 'outputs': records,
              'bytes': sum(record['bytes'] for record in records),
              'createdAt': datetime.now(timezone.utc).isoformat()}
    if apply:
        destination = root / 'build/reports'
        destination.mkdir(parents=True, exist_ok=True)
        receipt = destination / ('cleanup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.json')
        # Persist the plan before any removal; retain logs, receipts and source snapshots.
        receipt.write_text(json.dumps(dict(report, applied=False), indent=2) + '\n')
        for record in records:
            path = Path(record['path'])
            inspect(root, str(path.relative_to(root)))
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        receipt.write_text(json.dumps(report, indent=2) + '\n')
        report['receipt'] = str(receipt)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=ROOT)
    parser.add_argument('--apply', action='store_true', help='Remove inspected outputs; default is a dry run')
    args = parser.parse_args()
    print(json.dumps(clean(args.repo_root, args.apply), indent=2))
