"""Plain-directory job persistence; no database and no font object graph."""

from __future__ import annotations

import copy
from collections import defaultdict
import json
import tempfile
import time
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4
from .saved_script import unresolved


class JobStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else Path(
            tempfile.mkdtemp(prefix="glyphs-mcp-jobs-")
        )
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = RLock()
        self._index = {}
        self._statuses = defaultdict(set)
        self._documents = defaultdict(set)
        self._unresolved = set()
        for path in self.root.glob("job_*/state.json"):
            try:
                value = self.get(path.parent.name)
                self._index[value["id"]] = value
            except KeyError:
                continue
        # Dict order is recency order after startup, refreshed only on a write.
        values = sorted(self._index.values(), key=lambda job: job['updatedAt'])
        self._index.clear()
        for value in values:
            self._remember(value)

    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(list(reversed(self._index.values())))

    def select(self, statuses, *, document_id=None, include_unresolved=False):
        """Copy only selected evidence; unresolved script failures are never terminal work."""
        with self._lock:
            identities = set().union(*(self._statuses.get(state, ()) for state in statuses))
            if include_unresolved:
                identities.update(self._unresolved)
            if document_id is not None:
                identities.intersection_update(self._documents.get(document_id, ()))
            return copy.deepcopy(sorted((self._index[key] for key in identities),
                                        key=lambda job: job['updatedAt'], reverse=True))

    def count(self, statuses):
        with self._lock:
            return sum(len(self._statuses.get(state, ())) for state in statuses)

    def recent(self, limit, *, exclude_statuses=()):
        with self._lock:
            selected = []
            if limit <= 0:
                return selected
            for value in reversed(self._index.values()):
                if value['status'] not in exclude_statuses:
                    selected.append(value)
                    if len(selected) == limit:
                        break
            return copy.deepcopy(selected)

    def create(self, document: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
        job_id = "job_" + uuid4().hex
        now = time.time()
        value = {
            "id": job_id,
            "status": "preparing",
            "document": copy.deepcopy(dict(document)),
            "request": copy.deepcopy(dict(request)),
            "sourceHash": None,
            "summary": None,
            "resultKind": None,
            "changeCount": 0,
            "sample": [],
            "error": None,
            "createdAt": now,
            "updatedAt": now,
            "phaseStartedAt": now,
        }
        path = self.path(job_id)
        path.mkdir(mode=0o700)
        self._write(value)
        return copy.deepcopy(value)

    def path(self, job_id: str) -> Path:
        name = str(job_id)
        if not name.startswith("job_") or any(part in name for part in ("/", "\\", "..")):
            raise KeyError("invalid job ID")
        return self.root / name

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            path = self.path(job_id) / "state.json"
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError) as exc:
                raise KeyError(str(job_id)) from exc
            if not isinstance(value, dict) or value.get("id") != str(job_id):
                raise KeyError(str(job_id))
            return value

    def update(self, job_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            value = self.get(job_id)
            if all(key in value and value[key] == item for key, item in changes.items()):
                return value  # Fresh disk read, no changed evidence to persist.
            if changes.get("status", value["status"]) != value["status"] or changes.get("phase", value.get("phase")) != value.get("phase"):
                value["phaseStartedAt"] = time.time()
                value.pop("finishedAt", None)
            value.update(copy.deepcopy(changes))
            value["updatedAt"] = time.time()
            if value["status"] not in {"preparing", "cancelling", "applying", "accepting", "discarding"}:
                value.setdefault("finishedAt", value["updatedAt"])
            self._write(value)
            return copy.deepcopy(value)

    def write_json(self, job_id: str, name: str, value: Any) -> Path:
        if not name.endswith(".json") or "/" in name or "\\" in name:
            raise ValueError("job artifacts must be simple JSON filenames")
        path = self.path(job_id) / name
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(path)
        return path

    def read_json(self, job_id: str, name: str) -> Any:
        return json.loads((self.path(job_id) / name).read_text(encoding="utf-8"))

    def release_bulk_artifacts(self, job_id: str) -> None:
        root = self.path(job_id)
        for item in root.iterdir():
            if item.name in {"state.json", "receipt.json", "action-scope.json", "checkpointBaseline", "checkpointTransaction"}:
                continue
            if item.is_dir() and not item.is_symlink():
                import shutil

                try:
                    shutil.rmtree(item)
                except FileNotFoundError:
                    pass  # Another completion read already released this directory.
            else:
                item.unlink(missing_ok=True)

    def _write(self, value: Mapping[str, Any]) -> None:
        with self._lock:
            self.write_json(str(value["id"]), "state.json", dict(value))
            self._remember(copy.deepcopy(dict(value)))

    def _remember(self, value):
        identity = value['id']
        previous = self._index.pop(identity, None)
        if previous is not None:
            self._statuses[previous['status']].discard(identity)
            self._documents[previous['document']['id']].discard(identity)
        self._index[identity] = value
        self._statuses[value['status']].add(identity)
        self._documents[value['document']['id']].add(identity)
        self._unresolved.discard(identity)
        if unresolved(value):
            self._unresolved.add(identity)
