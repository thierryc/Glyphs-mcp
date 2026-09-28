"""Paired serial fresh-process history scaling, five repetitions per case."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
for history in (0, 100, 1000, 10000):
    for active in (False, True):
        for repeat in range(1, 6):
            for route in ('baseline', 'candidate'):
                source = ROOT/'build/beta8-milestone4/baseline' if route == 'baseline' else ROOT
                output = ROOT/f'reports/beta8-milestone4/matrix/{route}-{history}-{active}-{repeat}.json'
                if output.exists():
                    raise RuntimeError('Preserve recorded evidence: '+str(output))
                subprocess.run([sys.executable, '-B', str(ROOT/'scripts/benchmark_active_work.py'),
                    '--root', str(source), '--history', str(history), '--output', str(output)]
                    + (['--active'] if active else []), check=True, timeout=180)
        print(history, active, 'five paired repetitions complete', flush=True)
