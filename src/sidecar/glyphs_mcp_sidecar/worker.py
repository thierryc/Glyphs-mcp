"""One-shot plug-in-free glyphs-cli job launcher."""

from __future__ import annotations

import inspect
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from threading import Event, RLock
from typing import Any, Mapping

import glyphs_mcp_protocol
from glyphs_mcp_protocol import validate_patch


class WorkerError(RuntimeError):
    pass


WORKER_ERROR_PREFIX = "GLYPHS_MCP_WORKER_ERROR:"


class GlyphsCliWorker:
    def __init__(
        self,
        *,
        executable: str | None = None,
        app: str | None = None,
        timeout: float = 120.0,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.environment = dict(environment or os.environ)
        self.configured_executable = executable
        self.app = str(app or self.environment.get("GLYPHS_MCP_GLYPHS_APP") or "").strip()
        self.timeout = max(1.0, float(timeout))
        self._lock = RLock()
        self._executions = {}

    def executable(self) -> str | None:
        configured = str(
            self.configured_executable
            or self.environment.get("GLYPHS_MCP_GLYPHS_CLI")
            or ""
        ).strip()
        if configured:
            path = Path(configured)
            return str(path.resolve()) if path.is_absolute() and path.is_file() and os.access(path, os.X_OK) else None
        for candidate in (
            shutil.which("glyphs") or "",
            "/Library/Frameworks/Python.framework/Versions/Current/bin/glyphs",
        ):
            if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
                return str(Path(candidate).resolve())
        return None

    def status(self) -> dict[str, Any]:
        executable = self.executable()
        with self._lock:
            executions = [dict(value) for value in self._executions.values()]
        return {
            "available": bool(executable and self.app),
            "executable": executable,
            "application": self.app or None,
            "plugins": "disabled",
            "processModel": "one_shot",
            "executions": executions,
        }

    def prepare(
        self,
        job_root: Path,
        document: Mapping[str, Any],
        request: Mapping[str, Any],
        source_path: Path,
        source_hash: str,
        cancel: Event,
    ) -> dict[str, Any]:
        executable = self.executable()
        if executable is None or not self.app:
            raise WorkerError("glyphs-cli and an exact Glyphs application are required")
        request_path = job_root / "worker-request.json"
        output_path = job_root / "patch.json"
        payload = {
            "jobId": job_root.name,
            "document": dict(document),
            "request": dict(request),
            "source": str(source_path),
            "sourceHash": source_hash,
            "output": str(output_path),
        }
        request_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        sidecar_root = Path(__file__).resolve().parent.parent
        protocol_root = Path(inspect.getfile(glyphs_mcp_protocol)).resolve().parent.parent
        environment = dict(self.environment)
        environment["PYTHONPATH"] = os.pathsep.join(
            item
            for item in (
                str(sidecar_root),
                str(protocol_root),
                environment.get("PYTHONPATH", ""),
            )
            if item
        )
        command = [
            executable,
            "run",
            "--quiet",
            "--app",
            self.app,
            "--plugins",
            "",
            "-m",
            "glyphs_mcp_sidecar.native_worker",
            "--",
            str(request_path),
        ]
        with self._lock:
            self._executions[job_root.name] = {"jobId": job_root.name, "pid": None, "phase": "starting", "startedAt": time.time()}
        try:
            process = subprocess.Popen(
                command, cwd=str(job_root), env=environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            with self._lock:
                self._executions[job_root.name].update(pid=process.pid, phase="running")
            stdout, stderr = self._communicate(process, cancel)
        finally:
            with self._lock:
                self._executions.pop(job_root.name, None)
        if process.returncode != 0:
            for line in (stdout + "\n" + stderr).splitlines():
                if line.startswith(WORKER_ERROR_PREFIX):
                    try:
                        message = json.loads(line[len(WORKER_ERROR_PREFIX):])
                    except json.JSONDecodeError:
                        continue
                    if isinstance(message, str) and message:
                        raise WorkerError(message)
            detail = (stderr or stdout or "glyphs-cli job failed").strip()[-2000:]
            raise WorkerError(detail)
        try:
            value = json.loads(output_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise WorkerError("glyphs-cli returned no valid patch") from exc
        return validate_patch(value)

    def _communicate(self, process, cancel):
        started = time.monotonic()
        while True:
            if cancel.is_set():
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                raise WorkerError("job cancelled")
            if time.monotonic() - started > self.timeout:
                process.kill()
                process.wait(timeout=2)
                raise WorkerError("glyphs-cli job timed out")
            try:
                return process.communicate(timeout=0.1)
            except subprocess.TimeoutExpired:
                continue
