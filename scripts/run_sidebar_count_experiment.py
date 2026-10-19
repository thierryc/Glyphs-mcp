#!/usr/bin/env python3
"""Supervise fresh plugin-free Glyphs processes; never connect to the editor."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from sidebar_count_experiment import VARIANTS, classify

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def terminate_child(process):
    # This group was created by this supervisor, never discovered by app name.
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            process.wait(timeout=3)
            return
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=3)


def alert_recorded(events):
    if not events.exists():
        return False
    # A reader may see the last append before its trailing newline arrives.
    return any(json.loads(line).get("event") == "alert"
               for line in events.read_text().splitlines(keepends=True)
               if line.endswith("\n") and line.strip())


def supervise(cli, app, directory, variant, repeat, timeout, preflight=False):
    directory.mkdir()
    output = directory / "result.json"
    events = directory / "events.jsonl"
    command = [cli, "run", "--app", app, "--plugins", "",
               str(ROOT / "scripts/qualify_sidebar_counts_native.py"), "--",
               "--output", str(output), "--variant", variant]
    if preflight:
        command.append("--preflight")
    started = time.monotonic()
    outcome = None
    environment = dict(os.environ, GLYPHS_MCP_SIDEBAR_REPORT_DIR=str(directory.resolve()),
                       GLYPHS_MCP_SIDEBAR_PARENT_PGID=str(os.getpgrp()))
    with (directory / "stdout.log").open("w") as stdout, (directory / "stderr.log").open("w") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                   start_new_session=True, env=environment)
        try:
            while process.poll() is None:
                # The native observer only records; it never dismisses an alert.
                if alert_recorded(events):
                    outcome = "alert"
                    break
                if time.monotonic() - started >= timeout:
                    outcome = "timeout"
                    break
                time.sleep(.1)
        finally:
            terminate_child(process)
    native = json.loads(output.read_text()) if output.exists() else {}
    # An alert can be recorded immediately before normal process exit.
    if alert_recorded(events):
        outcome = "alert"
    result = dict(variant=variant, repeat=repeat, outcome=outcome or native.get("outcome", "failed"),
                  exitCode=process.returncode, seconds=time.monotonic()-started,
                  command=command, directory=str(directory), native=native)
    if result["outcome"] == "passed" and process.returncode != 0:
        result["outcome"] = "failed"
    write_json(directory / "supervisor.json", result)
    return result


def sources():
    paths = [ROOT / "scripts" / name for name in (
        "run_sidebar_count_experiment.py", "qualify_sidebar_counts_native.py",
        "sidebar_count_experiment.py", "native_script_harness.py")]
    paths += [path for part in ("bridge", "sidecar", "protocol")
              for path in sorted((ROOT / "src" / part).rglob("*.py"))]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", default="/Library/Frameworks/Python.framework/Versions/3.14/bin/glyphs")
    parser.add_argument("--app", default="/Applications/Glyphs 4.app")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    if args.repeats < 1 or args.timeout <= 0:
        parser.error("repeats and timeout must be positive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report = (args.report or ROOT / "reports" / ("sidebar-counts-" + stamp)).resolve()
    report.mkdir(parents=True, exist_ok=False)
    data = dict(classification="failed or blocked", repeats=args.repeats, glyphCount=1000,
                sourceHashes=sources(), transport="In-process SidecarService/BridgeCore; no HTTP or installed-client qualification",
                productionSuppression=False, runs=[], plannedRuns=4*args.repeats)
    write_json(report / "summary.json", data)
    try:
        preflight = supervise(args.cli, args.app, report / "preflight", "baseline", 0, args.timeout, True)
        data["preflight"] = preflight
        if preflight["outcome"] == "passed":
            for variant in VARIANTS:
                for repeat in range(1, args.repeats + 1):
                    run = supervise(args.cli, args.app, report / f"{variant}-{repeat}", variant, repeat, args.timeout)
                    data["runs"].append(run)
                    write_json(report / "summary.json", data)
                    print(f"{variant}-{repeat}: {run['outcome']}", flush=True)
            data["classification"] = classify(data["runs"], args.repeats)
        else:
            data["reason"] = "Isolated Font View/sidebar preflight did not pass; matrix was not run. No working-session fallback."
    except BaseException as error:
        data["supervisorError"] = repr(error)
        raise
    finally:
        write_json(report / "summary.json", data)
        print(json.dumps(dict(report=str(report), classification=data["classification"],
                              completedRuns=len(data["runs"]), plannedRuns=data["plannedRuns"])), flush=True)
    return 0 if data["classification"] in {"not reproduced", "promising mitigation"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
