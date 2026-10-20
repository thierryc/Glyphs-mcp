#!/usr/bin/env python3
"""Externally supervise subprocess capture with normal and single-worker pools."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def qualify():
    results = []
    with tempfile.TemporaryDirectory(prefix='gmcp-process-pool-') as directory:
        probe = Path(directory) / 'probe'
        subprocess.run(['xcrun', 'swiftc', '-parse-as-library',
                        str(ROOT / 'macos-installer/GlyphsMCPInstaller/Core/ProcessRunner.swift'),
                        str(ROOT / 'scripts/fixtures/process-runner-pool.swift'), '-o', str(probe)],
                       check=True, capture_output=True, text=True, timeout=60)
        for strict in (False, True):
            environment = dict(os.environ)
            environment.pop('LIBDISPATCH_COOPERATIVE_POOL_STRICT', None)
            if strict:
                environment['LIBDISPATCH_COOPERATIVE_POOL_STRICT'] = '1'
            for mode in ('capture', 'timeout', 'cancel', 'limit', 'launch-failure'):
                started = time.monotonic()
                try:
                    value = subprocess.run([str(probe), mode], env=environment, capture_output=True,
                                           text=True, timeout=8)
                    item = dict(mode=mode, strictPool=strict, exitCode=value.returncode,
                                stdout=value.stdout, stderr=value.stderr,
                                passed=value.returncode == 0 and value.stdout.strip() == 'passed:' + mode)
                except subprocess.TimeoutExpired:
                    item = dict(mode=mode, strictPool=strict, externalTimeout=True, passed=False)
                item['elapsedSeconds'] = round(time.monotonic() - started, 3)
                results.append(item)
    return dict(passed=all(item['passed'] for item in results), cases=results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = qualify()
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end='')
    raise SystemExit(0 if result['passed'] else 1)
