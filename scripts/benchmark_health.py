#!/usr/bin/env python3
"""Measure the isolated health observer, without touching a running Glyphs font."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for component in ('protocol', 'bridge'):
    sys.path.insert(0, str(ROOT / 'src' / component))
from glyphs_mcp_bridge.health import HealthMonitor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=600)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.duration <= 0 or args.output.exists():
        parser.error('Use a positive duration and a new output path.')
    queue = []
    monitor = HealthMonitor('isolated-benchmark')
    monitor.start(SimpleNamespace(health_inventory=lambda: dict(fontCount=0, unsavedCount=0,
        editTabCount=0, complete=True)), queue.append, lambda: False)
    latencies = []
    for _ in range(1000):
        started = time.perf_counter()
        monitor.snapshot()
        latencies.append(time.perf_counter() - started)
    cpu, wall = time.process_time(), time.monotonic()
    deadline = wall + args.duration
    try:
        while time.monotonic() < deadline:
            time.sleep(min(1, max(0, deadline - time.monotonic())))
        elapsed = time.monotonic() - wall
        cpu_used = time.process_time() - cpu
        health = monitor.snapshot()
        report = dict(scope='isolated observer; not loaded-Glyphs/native-job qualification',
            durationSeconds=elapsed, cpuSeconds=cpu_used, cpuPercentOneCore=100 * cpu_used / elapsed,
            snapshotP95Seconds=sorted(latencies)[949], samples=len(monitor.history),
            pendingNativeCallbacks=len(queue), health=health,
            gates=dict(fullIdleDuration=elapsed >= 600, cpu=cpu_used / elapsed < .005,
                       cachedLatency=sorted(latencies)[949] < .1, noIdleNativeCallbacks=not queue))
    finally:
        monitor.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'health'}, indent=2))


if __name__ == '__main__': main()
