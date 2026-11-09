#!/usr/bin/env python3
"""Measure passive status/health latency of the installed Glyphs session.

Read-only: never opens fonts, starts jobs, probes the native scheduler, injects
pressure, or changes settings. Run separately from job-duration/idle-CPU gates.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import plistlib
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requests', type=int, default=100)
    parser.add_argument('--clients', type=int, default=4)
    parser.add_argument('--p95-ms', type=float, default=100)
    parser.add_argument('--bridge-port', type=int, default=9681)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 20 <= args.requests <= 1000 or not 1 <= args.clients <= 8 or args.p95_ms <= 0:
        parser.error('Use 20–1000 requests, 1–8 clients, and a positive latency gate.')
    if args.output.exists(): parser.error('Use a new output path to retain previous evidence.')
    home = Path.home()
    settings = plistlib.loads((home / 'Library/LaunchAgents/com.ap.cx.glyphs-mcp-sidecar.plist').read_bytes())
    program = settings['ProgramArguments']
    port = int(program[program.index('--port') + 1]) if '--port' in program else 9680
    configured = settings.get('EnvironmentVariables', {}).get('GLYPHS_MCP_BRIDGE_TOKEN_FILE')
    token = (Path(configured).expanduser() if configured else home / 'Library/Application Support/Glyphs MCP/bridge-token').read_text().strip()
    report = dict(observedAt=datetime.now(timezone.utc).isoformat(), clients=args.clients,
                  scope='Installed passive HTTP status and health; no native mutation or pressure injection.',
                  p95GateMilliseconds=args.p95_ms, endpoints={})
    for label, endpoint, post in [('bridge', f'http://127.0.0.1:{args.bridge_port}/v1/status', True),
                                   ('companion', f'http://127.0.0.1:{port}/internal/status', False)]:
        def read(_):
            request = Request(endpoint, data=b'{}' if post else None,
                              headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            start = time.perf_counter()
            try:
                with urlopen(request, timeout=3) as response: value = json.load(response)
                if not value.get('ok'): raise ValueError('Status response refused')
                data = value['data']
                health = data.get('health') or {}
                return dict(milliseconds=(time.perf_counter() - start) * 1000,
                            version=data.get('sidecarVersion') or data.get('bridgeVersion'),
                            codeHash=data.get('codeHash'), health=health,
                            statusObservation=data.get('statusObservation'))
            except Exception as error:
                return dict(milliseconds=(time.perf_counter() - start) * 1000, error=str(error))
        with ThreadPoolExecutor(max_workers=args.clients) as pool:
            results = list(pool.map(read, range(args.requests)))
        latencies = sorted(result['milliseconds'] for result in results)
        errors = [result['error'] for result in results if 'error' in result]
        latest = next((result for result in reversed(results) if 'error' not in result), {})
        p95 = latencies[int(len(latencies) * .95) - 1]
        health = latest.get('health') or {}
        available = health.get('available') is True and health.get('version') == 1
        fresh = not (latest.get('statusObservation') or {}).get('stale', False)
        report['endpoints'][label] = dict(requests=len(results), errors=len(errors),
            firstError=errors[0] if errors else None, p95Milliseconds=p95,
            maxMilliseconds=max(latencies), version=latest.get('version'), codeHash=latest.get('codeHash'),
            health=health, passed=not errors and p95 < args.p95_ms and available and fresh)
    sessions = {item['health'].get('bridgeSessionId') for item in report['endpoints'].values()}
    report['matchingBridgeSession'] = len(sessions) == 1 and None not in sessions
    report['passed'] = report['matchingBridgeSession'] and all(item['passed'] for item in report['endpoints'].values())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(passed=report['passed'], output=str(args.output), endpoints={
        key: {name: value[name] for name in ('p95Milliseconds', 'errors', 'passed')}
        for key, value in report['endpoints'].items()})))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
