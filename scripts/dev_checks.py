#!/usr/bin/env python3
"""Run measured development checks. Release qualification remains a separate gate."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from test_selection import SCOPES, changed_paths, select_tests
from release_test_inputs import fingerprint

ROOT = Path(__file__).resolve().parents[1]


def python_command(root, plan, profile, output):
    marker = {'fast': 'not integration and not stress and not dependency',
              'component': 'not stress and not dependency',
              'full': 'not stress and not dependency',
              'performance': 'performance or stress'}[profile]
    return ['bash', str(root / 'scripts/run_python_tests.sh'), '--pytest', *plan['tests'],
            '-q', '-m', marker, '--durations=15', '--junitxml=' + str(output / 'python.xml'),
            '--test-report=' + str(output / 'python.md')] + (['--performance-gates'] if profile == 'performance' else [])


def summarize_junit(path):
    cases = list(ET.parse(path).getroot().iter('testcase'))
    return dict(cases=len(cases), failed=sum(c.find('failure') is not None or c.find('error') is not None for c in cases),
                skipped=sum(c.find('skipped') is not None for c in cases),
                slowest=sorted((dict(name=c.get('classname', '') + '::' + c.get('name', ''),
                                    seconds=float(c.get('time', 0))) for c in cases),
                               key=lambda c: c['seconds'], reverse=True)[:15])


def run(root, plan, profile, output, *, runner=subprocess.run, input_fingerprint=None, started=None):
    start = time.perf_counter() if started is None else started
    environment = dict(os.environ, PYTHON_BIN=sys.executable)
    environment.pop('GLYPHS_MCP_FULL_PYTHON_MATRIX', None)
    commands = [('python', python_command(root, plan, profile, output))]
    if profile in {'component', 'full'} and (plan['native'] or profile == 'full'):
        commands.append(('desktop', ['bash', str(root / 'scripts/run_desktop_checks.sh')]
                         + (['--app'] if plan.get('nativeApp') or profile == 'full' else [])))
    if profile in {'component', 'full'} and (plan['docs'] or profile == 'full'):
        commands.append(('documentation', ['npm', '--prefix', str(root / 'website'), 'run', 'build']))
    before = fingerprint(root) if input_fingerprint is None else input_fingerprint
    report = dict(profile=profile, scope=plan, qualifiedRelease=False, startedAt=datetime.now(timezone.utc).isoformat(), lanes=[])
    status = 0
    for name, command in commands:
        at = time.perf_counter()
        with (output / (name + '.log')).open('w') as log:
            result = runner(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT)
        report['lanes'].append(dict(name=name, seconds=time.perf_counter() - at, exitCode=result.returncode))
        print(f'{name}: exit {result.returncode}, {report["lanes"][-1]["seconds"]:.2f}s; {output / (name + ".log")}', flush=True)
        if result.returncode:
            status = result.returncode
            break
    if (output / 'python.xml').exists():
        report['python'] = summarize_junit(output / 'python.xml')
        if report['python']['failed']: status = status or 1
        if report['python']['cases'] <= report['python']['skipped']: status = status or 5
    elif not status:
        status = 5  # A successful launcher without test evidence is not a pass.
    report['inputsUnchanged'] = fingerprint(root) == before
    if not report['inputsUnchanged']: status = status or 1
    report.update(seconds=time.perf_counter() - start, exitCode=status, passed=status == 0)
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    return status


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['fast', 'component', 'full', 'performance', 'release'], default='fast')
    parser.add_argument('--scope', choices=sorted(SCOPES), help='Explicit partial check, not qualification of all changes')
    parser.add_argument('--base-ref', default='HEAD')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.profile == 'full' and args.scope: parser.error('Full checks cannot be restricted to a scope.')
    if args.profile == 'release':
        if args.scope: parser.error('Release qualification cannot be restricted to a scope.')
        if args.dry_run:
            print('bash scripts/run_local_release_tests.sh --serial'); return 0
        return subprocess.call(['bash', str(ROOT / 'scripts/run_local_release_tests.sh'), '--serial'], cwd=ROOT,
                               env=dict(os.environ, PYTHON_BIN=sys.executable))
    before = fingerprint(ROOT) if not args.dry_run else None
    paths = changed_paths(ROOT, args.base_ref)
    plan = select_tests(ROOT, paths, scope=args.scope)
    if args.profile in {'full', 'performance'} and not args.scope:
        plan['tests'] = [str(Path('src/glyphs-mcp/tests'))]
    if args.dry_run:
        print(json.dumps(dict(profile=args.profile, **plan), indent=2)); return 0
    output_root = ROOT / 'build/dev-checks'
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output = Path(tempfile.mkdtemp(prefix=args.profile + '-', dir=output_root))
        (output / 'selection.json').write_text(json.dumps(plan, indent=2) + '\n')
        print(f'Profile: {args.profile}; selection: {plan["selectionMode"]}; reports: {output}', flush=True)
        for reason in plan['reasons']: print(reason, flush=True)
        return run(ROOT, plan, args.profile, output, input_fingerprint=before, started=started)


if __name__ == '__main__':
    raise SystemExit(main())
