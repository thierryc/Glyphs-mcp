"""Serial, fresh-process capacity matrix with shared immutable native fixtures."""
import argparse
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--report', type=Path, required=True)
parser.add_argument('--baseline', type=Path, required=True)
parser.add_argument('--candidate', type=Path, default=ROOT)
parser.add_argument('--fixtures', type=Path, required=True)
parser.add_argument('--fixtures-only', action='store_true')
args = parser.parse_args()
args.report.mkdir(parents=True, exist_ok=True)
args.fixtures.mkdir(parents=True, exist_ok=True)
logs = ROOT/'build/beta8-milestone1/benchmark-logs'; logs.mkdir(parents=True, exist_ok=True)
cases = [(n, 1) for n in (1000, 4096, 10000, 20000)] + [(10000, 4), (20000, 4)]


def invoke(root, name, count, contours, suffix, mode='native', extra=()):
    output = args.report/(name+'.json')
    if output.exists():
        assert json.loads(output.read_text()).get('passed'), f'Prior failed evidence: {output}'
        return
    command = ['glyphs', 'run', '--quiet', '--app', '/Applications/Glyphs 4.app', '--plugins', '',
        str(root/'scripts/benchmark_script_capacity.py'), '--', '--count', str(count), '--contours',
        str(contours), '--format', suffix, '--mode', mode, '--fixtures', str(args.fixtures.resolve()),
        '--output', str(output.resolve()), *extra]
    started = time.perf_counter()
    with (logs/(name+'.log')).open('w') as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=900)
    row = json.loads(output.read_text()) if output.exists() else {}
    passed = result.returncode == 0 and row.get('passed')
    progress.append(dict(name=name, passed=bool(passed), processSeconds=time.perf_counter()-started))
    (args.report/'progress.json').write_text(json.dumps(progress, indent=2)+'\n')
    print(name+(' PASS' if passed else ' FAIL'), flush=True)
    if not passed: raise RuntimeError(name)


progress_path = args.report/'progress.json'
progress = ([row for row in json.loads(progress_path.read_text()) if row['passed']]
            if progress_path.exists() else [])
for count, contours in cases:
    for suffix in ('glyphs', 'glyphspackage'):
        fixture = args.fixtures/f'{count}-{contours}.{suffix}'
        if not fixture.exists():
            invoke(args.candidate, f'fixture-{count}-{contours}-{suffix}', count, contours, suffix,
                   extra=['--prepare-fixture'])
if args.fixtures_only: raise SystemExit(0)

for count, contours in cases:
    for suffix in ('glyphs', 'glyphspackage'):
        for repeat in range(1, 6):
            routes = [('candidate', args.candidate, 'native'), ('direct', args.candidate, 'direct')]
            if count <= 4096: routes.insert(0, ('baseline', args.baseline, 'native'))
            for label, root, mode in routes:
                invoke(root, f'{label}-{count}-{contours}-{suffix}-{repeat}', count, contours, suffix, mode)
for suffix in ('glyphs', 'glyphspackage'):
    for repeat in range(1, 6):
        invoke(args.candidate, f'dirty-1000-1-{suffix}-{repeat}', 1000, 1, suffix, extra=['--dirty'])
