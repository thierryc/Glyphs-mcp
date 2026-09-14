#!/usr/bin/env python3
"""Run one phase of the lean v2 live gate against a disposable saved font."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Callable


REPO = Path(__file__).resolve().parents[1]
DEFAULT_PAYLOAD = REPO / "build" / "simple-v2"


def _load_runtime(payload: Path) -> tuple[Any, Any, Any, Any, Any]:
    sidecar = payload.resolve() / "sidecar"
    sys.path.insert(0, str(sidecar))
    from glyphs_mcp_protocol import load_or_create_token
    from glyphs_mcp_sidecar.bridge_client import BridgeClient
    from glyphs_mcp_sidecar.jobs import JobStore
    from glyphs_mcp_sidecar.service import SidecarService
    from glyphs_mcp_sidecar.worker import GlyphsCliWorker

    return load_or_create_token, BridgeClient, JobStore, SidecarService, GlyphsCliWorker


def _write(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("the live-gate record is invalid")
    return value


def _document(client: Any, source: Path) -> dict[str, Any]:
    expected = str(source.resolve())
    documents = client.documents()
    if len(documents) != 1:
        paths = [str(value.get("path") or "Untitled") for value in documents]
        raise RuntimeError(
            "the live gate requires exactly one open disposable document; found: "
            + ", ".join(paths)
        )
    matches = [
        value
        for value in documents
        if value.get("path") and str(Path(value["path"]).resolve()) == expected
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one open disposable document at {expected!r}")
    return matches[0]


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _measurement(values: list[float]) -> dict[str, Any]:
    milliseconds = [value * 1000 for value in values]
    return {
        "samples": len(milliseconds),
        "p50Ms": round(_percentile(milliseconds, 0.50), 3),
        "p95Ms": round(_percentile(milliseconds, 0.95), 3),
        "maxMs": round(max(milliseconds), 3),
    }


def _poll(
    callback: Callable[[], dict[str, Any]],
    probe: Callable[[], Any],
    *,
    terminal: set[str],
    timeout: float,
    interval: float,
    minimum_samples: int = 10,
    settle_seconds: float = 0.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    terminal_at: float | None = None
    samples: list[float] = []
    result: dict[str, Any] = {}
    while True:
        before = time.monotonic()
        probe()
        samples.append(time.monotonic() - before)
        result = callback()
        now = time.monotonic()
        if result.get("status") in terminal and terminal_at is None:
            terminal_at = now
        if (
            terminal_at is not None
            and len(samples) >= minimum_samples
            and now - terminal_at >= settle_seconds
        ):
            break
        elapsed = now - started
        if elapsed >= timeout:
            raise TimeoutError(f"live phase exceeded {timeout:.0f} seconds")
        time.sleep(max(0.0, interval - (time.monotonic() - before)))
    measurement = _measurement(samples)
    measurement["durationSeconds"] = round(time.monotonic() - started, 3)
    return result, measurement


def _service(args: argparse.Namespace) -> tuple[Any, Any]:
    token_loader, BridgeClient, JobStore, SidecarService, GlyphsCliWorker = _load_runtime(
        args.payload
    )
    client = BridgeClient(args.bridge, token_loader(), timeout=10.0)
    worker = GlyphsCliWorker(
        executable=args.glyphs_cli,
        app=str(args.glyphs_app),
        timeout=args.timeout,
    )
    return client, SidecarService(client, jobs=JobStore(args.jobs), worker=worker)


def _assert_responsive(measurement: dict[str, Any]) -> None:
    if measurement["samples"] < 10:
        raise RuntimeError("the live gate collected fewer than ten main-queue samples")
    if measurement["p95Ms"] >= 50:
        measurement["p95Diagnostic"] = "Investigate reproducible loaded latency against baseline"
    if measurement["maxMs"] >= 200:
        measurement["maxDiagnostic"] = "Above 200 ms: distinguish modal waiting from native execution"


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    client, service = _service(args)
    document = _document(client, args.source)
    if document.get("dirty") is not False:
        raise RuntimeError("the disposable document must be saved and clean")
    from glyphs_mcp_sidecar.source import source_hash

    baseline_hash = source_hash(args.source)
    started = service.start_job(
        document["id"], kind="width_delta", delta=args.delta, glyphs=None
    )
    job, responsiveness = _poll(
        lambda: service.get_job(started["id"]),
        client.status,
        terminal={"ready", "failed", "cancelled"},
        timeout=args.timeout,
        interval=args.interval,
    )
    if job.get("status") != "ready":
        raise RuntimeError(f"external preparation ended as {job.get('status')}: {job.get('error')}")
    _assert_responsive(responsiveness)
    after_document = _document(client, args.source)
    after_hash = source_hash(args.source)
    if after_document != document:
        raise RuntimeError("external preparation changed the live document state")
    if after_hash != baseline_hash:
        raise RuntimeError("external preparation changed the disposable saved source")
    record = {
        "version": 1,
        "phase": "ready",
        "source": str(args.source.resolve()),
        "sourceHash": baseline_hash,
        "document": document,
        "job": job,
        "prepareResponsiveness": responsiveness,
    }
    _write(args.record, record)
    return record


def apply(args: argparse.Namespace) -> dict[str, Any]:
    record = _read(args.record)
    client, service = _service(args)
    source = Path(record["source"])
    if _document(client, source) != record["document"]:
        raise RuntimeError("the disposable document changed before application")
    started = service.apply_job(record["job"]["id"])
    job, responsiveness = _poll(
        lambda: service.get_job(started["id"]),
        client.status,
        terminal={"applied", "failed", "cancelled"},
        timeout=args.timeout,
        interval=args.interval,
        settle_seconds=2.0,
    )
    if job.get("status") != "applied":
        raise RuntimeError(f"application ended as {job.get('status')}: {job.get('error')}")
    _assert_responsive(responsiveness)
    if source_hash(source) != record["sourceHash"]:
        raise RuntimeError("application changed the saved source without a user Save")
    record.update(
        phase="applied_for_review",
        job=job,
        appliedDocument=_document(client, source),
        applyResponsiveness=responsiveness,
    )
    _write(args.record, record)
    return record


def discard(args: argparse.Namespace) -> dict[str, Any]:
    record = _read(args.record)
    client, service = _service(args)
    source = Path(record["source"])
    started = service.discard_job(record["job"]["id"])
    job, responsiveness = _poll(
        lambda: service.get_job(started["id"]),
        client.status,
        terminal={"discarded", "failed", "cancelled"},
        timeout=args.timeout,
        interval=args.interval,
        settle_seconds=2.0,
    )
    if job.get("status") != "discarded":
        raise RuntimeError(f"discard ended as {job.get('status')}: {job.get('error')}")
    _assert_responsive(responsiveness)
    if source_hash(source) != record["sourceHash"]:
        raise RuntimeError("discard changed the disposable saved source")
    record.update(
        phase="discarded",
        job=job,
        discardedDocument=_document(client, source),
        discardResponsiveness=responsiveness,
    )
    _write(args.record, record)
    return record


def source_hash(path: Path) -> str:
    from glyphs_mcp_sidecar.source import source_hash as calculate

    return calculate(path)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("phase", choices=("prepare", "apply", "discard"))
    value.add_argument("--payload", type=Path, default=DEFAULT_PAYLOAD)
    value.add_argument("--source", type=Path)
    value.add_argument("--jobs", type=Path, required=True)
    value.add_argument("--record", type=Path, required=True)
    value.add_argument("--bridge", default="http://127.0.0.1:9681")
    value.add_argument("--glyphs-cli", default="/Library/Frameworks/Python.framework/Versions/3.14/bin/glyphs")
    value.add_argument("--glyphs-app", type=Path, default=Path("/Applications/Glyphs 4.app"))
    value.add_argument("--delta", type=float, default=8.0)
    value.add_argument("--interval", type=float, default=0.02)
    value.add_argument("--timeout", type=float, default=120.0)
    return value


def main() -> int:
    args = parser().parse_args()
    if args.phase == "prepare" and args.source is None:
        raise SystemExit("--source is required for prepare")
    result = {"prepare": prepare, "apply": apply, "discard": discard}[args.phase](args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
