#!/usr/bin/env python3
"""Incremental development tests; never publishes an installable app/receipt."""
import argparse
import fcntl
import os
import json
from pathlib import Path
import subprocess
import sys
import time
from release_test_inputs import fingerprint

ROOT = Path(__file__).resolve().parents[1]


def commands(root, *, app=False, only=()):
    common = ['-project', str(root / 'macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj'),
              '-configuration', 'Debug', '-destination', 'platform=macOS',
              '-derivedDataPath', str(root / 'build/dev-desktop/DerivedData'),
              '-jobs', '4', 'CODE_SIGNING_ALLOWED=NO', 'CODE_SIGNING_REQUIRED=NO']
    result = []
    if app:
        result.append(['xcodebuild', 'build', '-scheme', 'GlyphsMCPInstaller', *common])
    result.append(['xcodebuild', 'test', '-scheme', 'GlyphsMCPCoreTests', *common,
                   '-skip-testing:GlyphsMCPInstallerTests/GlyphsMCPInstallerTests/testGeneratedBuildPayloadMatchesSwiftRuntimeIdentity',
                   *['-only-testing:GlyphsMCPInstallerTests/' + name for name in only]])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', action='store_true', help='Also compile application views with a verified development payload cache')
    parser.add_argument('--only-testing', action='append', default=[])
    args = parser.parse_args()
    if any(not name.replace('_', '').isalnum() for name in args.only_testing):
        parser.error('Use test class names, without paths or command options.')
    output = ROOT / 'build/dev-desktop'; output.mkdir(parents=True, exist_ok=True)
    with (output / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        env = dict(os.environ, PYTHON_BIN=sys.executable, GMCP_DEVELOPMENT_PAYLOAD_CACHE='1')
        start, before = time.perf_counter(), fingerprint(ROOT)
        report = dict(passed=False, qualifiedRelease=False, includesAppBuild=args.app, commands=[])
        result = output / 'check-result.json'
        result.write_text(json.dumps(report) + '\n')
        try:
            if args.app:
                subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_desktop_dependencies.py')], cwd=ROOT, env=env, check=True)
            for command in commands(ROOT, app=args.app, only=args.only_testing):
                at = time.perf_counter()
                completed = subprocess.run(command, cwd=ROOT, env=env)
                report['commands'].append(dict(action=command[1], seconds=time.perf_counter() - at, exitCode=completed.returncode))
                completed.check_returncode()
            report['inputsUnchanged'] = fingerprint(ROOT) == before
            if not report['inputsUnchanged']: raise RuntimeError('Desktop inputs changed during checks.')
            report['passed'] = True
        finally:
            report['seconds'] = time.perf_counter() - start
            result.write_text(json.dumps(report, indent=2) + '\n')
        print(f'Development desktop checks passed in {report["seconds"]:.2f}s; {result}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
