#!/usr/bin/env python3
"""Build a fresh, unsigned desktop app and publish it only after verification."""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from verify_desktop_app import ROOT, source_digest, verify


def build():
    output = ROOT / 'dist/local'
    output.mkdir(parents=True, exist_ok=True)
    # A failed or interrupted build must not leave a usable old receipt.
    receipt = output / 'build-receipt.json'
    receipt.unlink(missing_ok=True)
    app = output / 'Glyphs MCP.app'
    if app.exists():
        shutil.rmtree(app)
    subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_desktop_dependencies.py')], check=True)
    before = source_digest()
    runs = ROOT / 'build/local-app-runs'
    runs.mkdir(parents=True, exist_ok=True)
    reports = ROOT / 'build/reports'
    reports.mkdir(parents=True, exist_ok=True)
    log = reports / 'local-app-build.log'
    with tempfile.TemporaryDirectory(prefix='run-', dir=runs) as temporary:
        derived = Path(temporary)
        command = ['xcodebuild', 'build', '-project', str(ROOT / 'macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj'),
                   '-scheme', 'GlyphsMCPInstaller', '-configuration', 'Debug', '-destination', 'platform=macOS',
                   '-derivedDataPath', str(derived), 'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO']
        environment = dict(os.environ, PYTHON_BIN=sys.executable)
        print(f'Building in fresh directory: {derived}\nBuild log: {log}', flush=True)
        with log.open('w') as stream:
            subprocess.run(command, cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT, check=True)
        candidate = derived / 'Build/Products/Debug/Glyphs MCP.app'
        bundle = verify(candidate)
        if source_digest() != before:
            raise RuntimeError('Source changed during the build; no app was published. Rebuild.')
        subprocess.run(['/usr/bin/ditto', str(candidate), str(app)], check=True)
        if verify(app) != bundle:
            raise RuntimeError('Copied app does not match the verified build')
        receipt.write_text(json.dumps({'sourceRoot': str(ROOT), 'sourceSHA256': before,
                                      'bundle': bundle, 'builtAt': datetime.now(timezone.utc).isoformat()}, indent=2) + '\n')
    print(f'Verified app: {app}\nBuild receipt: {receipt}')


if __name__ == '__main__':
    lock = ROOT / 'build/local-app-build.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('w') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build()
