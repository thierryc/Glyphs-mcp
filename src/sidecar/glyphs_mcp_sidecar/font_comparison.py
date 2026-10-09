"""Compiled-font jobs. No live document, native operation, or font save."""
from __future__ import annotations

import hashlib
import copy
import json
import mimetypes
import os
from pathlib import Path
import platform
import selectors
import signal
import subprocess
from threading import Thread, Event
import time

from glyphs_mcp_protocol import canonical_json, ProtocolError
from glyphs_mcp_protocol.font_comparison import CAPABILITY, MAX_BYTES, options, validate_manifest

REVISION = "cecdab703d462cfea25b748b19ea4813d3f4d680"
DEFAULT_ROOT = Path.home() / "Library/Application Support/Glyphs MCP/optional-tools/diffenator"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


class ComparisonError(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


class ComparisonWorker:
    def __init__(self, root=DEFAULT_ROOT):
        self.root = Path(root)
        self._availability = self._inspect_status()

    def runtime(self):
        try:
            receipt = json.loads((self.root / "current.json").read_text())
            version = receipt["directory"]
            if not isinstance(version, str) or not version or Path(version).name != version or version in (".", ".."):
                raise ValueError("invalid runtime directory")
            root = self.root / version
            root.resolve().relative_to(self.root.resolve())
            manifest = json.loads((root / "runtime.json").read_text())
            if manifest.get("schemaVersion") != 1 or manifest.get("tool") != "diffenator2" or manifest.get("sourceRevision") != REVISION:
                raise ValueError("unqualified Diffenator revision")
            architecture = "arm64" if platform.machine() == "arm64" else "x86_64"
            if manifest.get("architecture") != architecture:
                raise ValueError("runtime architecture does not match this process")
            ownership = json.loads((self.root.parent / "receipt-diffenator.json").read_text())
            if ownership.get("target") != str(root) or ownership.get("directory") != version:
                raise ValueError("managed runtime receipt does not match the selected runtime")
            if root.is_symlink() or (root / "runtime.json").is_symlink():
                raise ValueError("managed runtime must not be a symbolic link")
            expected_manifest = ownership.get("files", {}).get(ownership.get("payloadRoot", "") + "/runtime.json")
            if expected_manifest != sha(root / "runtime.json").removeprefix("sha256:"):
                raise ValueError("runtime manifest differs from the verified installation")
            python = root / "bin/python3"
            if not python.is_file() or not os.access(python, os.X_OK):
                raise ValueError("runtime Python is unavailable")
            return root, python, manifest
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ComparisonError("comparison_runtime_unavailable", "Install Diffenator in Glyphs MCP Setup. " + str(exc)) from exc

    def _inspect_status(self):
        try:
            _, _, manifest = self.runtime()
            return {"available": True, "sourceRevision": manifest["sourceRevision"], "jobCapabilities": [CAPABILITY]}
        except ComparisonError as exc:
            return {"available": False, "jobCapabilities": [], "error": {"code": exc.code, "message": exc.message}}

    def status(self):
        # Setup replaces runtimes only while the sidecar is stopped. Cache the
        # discovery result for cheap activity polling; execution rechecks bytes.
        return copy.deepcopy(self._availability)

    def run(self, root, request, cancel):
        runtime_root, python, manifest = self.runtime()
        # Setup authenticated the distribution; recheck its immutable inventory
        # before executing. Never resolve an ambient CLI or use shell=True.
        files = manifest.get("files")
        if not isinstance(files, dict) or not files or len(files) > 20000:
            raise ComparisonError("runtime_conflict", "Diffenator runtime inventory is unavailable")
        for relative, checksum in files.items():
            if cancel.is_set():
                raise ComparisonError("comparison_cancelled", "Comparison cancelled")
            if not isinstance(relative, str) or not isinstance(checksum, str):
                raise ComparisonError("runtime_conflict", "Invalid Diffenator runtime inventory")
            path = runtime_root / relative
            if Path(relative).is_absolute() or ".." in Path(relative).parts or path.is_symlink():
                raise ComparisonError("runtime_conflict", "Unsafe Diffenator runtime inventory")
            path.resolve().relative_to(runtime_root.resolve())
            if not path.is_file() or sha(path) != checksum:
                raise ComparisonError("runtime_conflict", "Diffenator runtime changed; reinstall it from Setup")
        expected = set(files) | {"runtime.json"}
        observed = {path.relative_to(runtime_root).as_posix() for path in runtime_root.rglob("*") if path.is_file()}
        if observed != expected or "bin/python3" not in files:
            raise ComparisonError("runtime_conflict", "Diffenator runtime inventory differs; reinstall it from Setup")
        request["unicodeData"] = str(runtime_root / "share/diffenator-ucd")
        (root / "comparison-request.json").write_text(json.dumps(request))
        command = [str(python), "-I", "-B", str(Path(__file__).with_name("diffenator_adapter.py")), str(root / "comparison-request.json")]
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        environment["PATH"] = str(runtime_root / "bin") + ":/usr/bin:/bin"
        run_process(command, root, environment, cancel)
        return {k: manifest[k] for k in ("sourceRevision", "architecture", "pythonVersion", "unicodeVersion") if k in manifest}


def run_process(command, cwd, environment, cancel, timeout=600):
    if cancel.is_set():
        raise ComparisonError("comparison_cancelled", "Comparison cancelled")
    process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    selector = selectors.DefaultSelector()
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        for stream in (process.stdout, process.stderr):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ)
        while selector.get_map() or process.poll() is None:
            if cancel.is_set():
                raise ComparisonError("comparison_cancelled", "Comparison cancelled")
            if time.monotonic() >= deadline:
                raise ComparisonError("comparison_timeout", "Comparison exceeded its ten-minute limit")
            for key, _ in selector.select(.05):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                else:
                    output.extend(chunk)
                    if len(output) > 1024 * 1024:
                        raise ComparisonError("comparison_output_limit", "Comparison log exceeded 1 MiB")
        if process.wait() != 0:
            raise ComparisonError("comparison_failed", output.decode("utf-8", "replace")[-4000:] or "Diffenator failed")
    finally:
        selector.close()
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            if sig == signal.SIGTERM:
                try:
                    process.wait(timeout=.25)
                except subprocess.TimeoutExpired:
                    pass
        process.wait()
        process.stdout.close()
        process.stderr.close()


def validate_paths(value, label):
    if not isinstance(value, list) or not 1 <= len(value) <= 32:
        raise ComparisonError("invalid_request", label + " must contain 1-32 absolute TTF paths")
    result = []
    for item in value:
        if not isinstance(item, str) or not item or len(item) > 4096 or "\0" in item:
            raise ComparisonError("invalid_request", "invalid font path")
        path = Path(item)
        if not path.is_absolute() or path.suffix.lower() != ".ttf" or not path.is_file():
            raise ComparisonError("invalid_request", "comparison requires existing absolute TTF files")
        path = path.resolve()
        if str(path) in result:
            raise ComparisonError("invalid_request", "duplicate font input")
        result.append(str(path))
    return result


def snapshot(path, destination, cancel, *, font=True):
    original = path.stat()
    limit = 32 * 1024 * 1024 if font else 1024 * 1024
    if original.st_size > limit:
        raise ComparisonError("input_limit", "Comparison input exceeds its size limit")
    total = 0
    with path.open("rb") as source, destination.open("xb") as output:
        while chunk := source.read(65536):
            if cancel.is_set():
                raise ComparisonError("comparison_cancelled", "Comparison cancelled")
            total += len(chunk)
            if total > limit:
                raise ComparisonError("input_limit", "Comparison input exceeds its size limit")
            output.write(chunk)
    if (original.st_ino, original.st_size, original.st_mtime_ns) != ((current := path.stat()).st_ino, current.st_size, current.st_mtime_ns):
        raise ComparisonError("input_changed", "A comparison input changed while it was copied")
    destination.chmod(0o600)
    if font:
        from fontTools.ttLib import TTFont
        try:
            with TTFont(destination) as binary:
                if "glyf" not in binary or not {"head", "name", "cmap", "OS/2"}.issubset(binary.keys()):
                    raise ValueError("not a supported compiled TrueType font")
                if "fvar" in binary and len(binary["fvar"].axes) > 8:
                    raise ValueError("variable font exceeds eight comparison axes")
        except Exception as exc:
            raise ComparisonError("invalid_font", str(exc)) from exc
    return {"path": str(path), "snapshot": destination.name, "size": total, "sha256": sha(destination)}


def start(service, error_type, baseline_files, candidate_files, supplied_options):
    try:
        normalized = options(supplied_options)
        baseline = validate_paths(baseline_files, "baseline_files")
        candidate = validate_paths(candidate_files, "candidate_files")
        if "userWordlist" in normalized:
            wordlist = Path(normalized["userWordlist"])
            if not wordlist.is_absolute() or not wordlist.is_file() or wordlist.suffix.lower() not in (".csv", ".txt"):
                raise ComparisonError("invalid_request", "userWordlist must be an absolute existing .txt or .csv file")
        if not service.comparison_worker.status().get("available"):
            raise ComparisonError("comparison_runtime_unavailable", "Install Diffenator in Glyphs MCP Setup before comparing fonts")
    except (ProtocolError, ComparisonError) as exc:
        raise error_type(exc.code, exc.message) from exc
    request = {"kind": "font_comparison", "baseline": baseline, "candidate": candidate, "options": normalized}
    job = service.jobs.create(None, request)
    service.jobs.update(job["id"], resultKind="artifact", inputKind="compiled_fonts")
    cancel = Event()
    with service._lock:
        service._cancellations[job["id"]] = cancel
    Thread(target=prepare, args=(service, job["id"], cancel), daemon=True, name="font-comparison-" + job["id"]).start()
    return service._public(service.jobs.get(job["id"]))


def prepare(service, job_id, cancel):
    root = service.jobs.path(job_id)
    try:
        job = service.jobs.get(job_id)
        request = job["request"]
        service.jobs.update(job_id, phase="snapshotting_inputs")
        inputs = {}
        for group in ("baseline", "candidate"):
            inputs[group] = [snapshot(Path(path), root / f"{group}-{index}.ttf", cancel) for index, path in enumerate(request[group])]
        normalized = dict(request["options"])
        if "userWordlist" in normalized:
            inputs["wordlist"] = snapshot(Path(normalized["userWordlist"]), root / ("words" + Path(normalized["userWordlist"]).suffix.lower()), cancel, font=False)
            normalized["userWordlist"] = str(root / inputs["wordlist"]["snapshot"])
        input_hash = "sha256:" + hashlib.sha256(canonical_json(inputs).encode()).hexdigest()
        service.jobs.write_json(job_id, "inputs.json", inputs)
        service.jobs.update(job_id, sourceHash=input_hash, inputs=inputs, phase="comparing_fonts")
        staged_request = {group: [str(root / item["snapshot"]) for item in inputs[group]] for group in ("baseline", "candidate")}
        staged_request.update(options=normalized, output=str(root / "artifacts"))
        service.jobs.write_json(job_id, "comparison-request.json", staged_request)
        runtime = service.comparison_worker.run(root, staged_request, cancel)
        if cancel.is_set():
            raise ComparisonError("comparison_cancelled", "Comparison cancelled")
        service.jobs.update(job_id, phase="verifying_report")
        report = {"completed": True, "inputs": inputs, "options": request["options"], "runtime": runtime,
                  "warnings": ["Differences require review; default wordlists do not cover every name or optional feature."],
                  "exportSettings": "unknown unless retained separately with the input exports"}
        artifacts = root / "artifacts"
        artifacts.mkdir(mode=0o700, exist_ok=True)
        scope_path = artifacts / "scope.json"
        if scope_path.exists():
            if scope_path.is_symlink() or scope_path.stat().st_size > 1024 * 1024:
                raise ComparisonError("report_limit", "Comparison scope exceeds its limit")
            scope = json.loads(scope_path.read_text())
            matched = scope.get("matchedStyles")
            if not isinstance(matched, list) or not 1 <= len(matched) <= 256:
                raise ComparisonError("invalid_report", "Comparison scope lacks matched styles")
            report["matchedStyles"] = matched
        (artifacts / "comparison.json").write_text(json.dumps(report, indent=2))
        files, total = [], 0
        for path in sorted(artifacts.rglob("*")):
            if path.is_symlink():
                raise ComparisonError("artifact_conflict", "Report contains a symbolic link")
            if path.is_dir():
                continue
            if not path.is_file():
                raise ComparisonError("artifact_conflict", "Report contains a special file")
            total += path.stat().st_size
            if total > MAX_BYTES or len(files) >= 4096:
                raise ComparisonError("report_limit", "Report exceeded its file or size limit")
            files.append({"path": path.relative_to(artifacts).as_posix(), "size": path.stat().st_size,
                          "sha256": sha(path), "mediaType": mimetypes.guess_type(path.name)[0] or "application/octet-stream"})
        manifest = validate_manifest({"files": files, "totalBytes": total, "entryPoint": "diffenator2-report.html"})
        service.jobs.write_json(job_id, "manifest.json", manifest)
        service.jobs.update(job_id, status="ready", summary="Font comparison completed; review the HTML report.", report=report,
                            manifest=manifest, entryPoint=str(artifacts / manifest["entryPoint"]))
    except Exception as exc:
        with service._lock:
            cancelled = cancel.is_set()
            service.jobs.update(job_id, status="cancelled" if cancelled else "failed",
                                error=None if cancelled else {"code": getattr(exc, "code", "comparison_failed"), "message": str(exc)})
        service.jobs.release_bulk_artifacts(job_id)
    finally:
        with service._lock:
            service._cancellations.pop(job_id, None)
