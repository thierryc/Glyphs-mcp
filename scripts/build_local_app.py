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


def require_stopped(app):
    executable = str(app.resolve() / 'Contents/MacOS/Glyphs MCP')
    try:
        processes = subprocess.check_output(['/bin/ps', '-axo', 'pid=,command='], text=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError('Cannot verify whether the local app is running; the candidate was preserved.') from error
    for line in processes.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) == 2 and (fields[1] == executable or fields[1].startswith(executable + ' ')):
            raise RuntimeError(f'Quit the local Glyphs MCP app (PID {fields[0]}) before rebuilding it. The candidate was preserved.')


def build():
    output = ROOT / 'dist/local'
    app = output / 'Glyphs MCP.app'
    # Never replace files beneath a live process: it can retain older executable
    # code while reading newer resources from the same bundle path.
    require_stopped(app)
    output.mkdir(parents=True, exist_ok=True)
    # A failed or interrupted build must not leave a usable old receipt.
    receipt = output / 'build-receipt.json'
    receipt.unlink(missing_ok=True)
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
        require_stopped(app)
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
