"""Content-addressed canonical font snapshots with glyph-level sharing.

The store receives detached JSON-safe models. Glyphs/AppKit objects never cross
this boundary, so hashing and persistence can run away from Glyphs' main thread.
"""

from __future__ import annotations

import copy
import contextlib
import hashlib
import os
import sqlite3
import zlib
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Protocol

from .semantic import ChangeSet, canonical_json, diff_models, fingerprint_model


TREE_SCHEMA_VERSION = 1
CANONICAL_MODEL_SCHEMA_VERSION = 2
REVERSIBILITY_COVERAGE = "modeled_fields_only"
SHARDED_MAPPING_ROOTS = frozenset({"glyphs", "kerning"})


def _object_hash(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


class ObjectStore(Protocol):
    def put(self, payload: bytes) -> tuple[str, bool]:
        ...

    def get(self, object_hash: str) -> bytes:
        ...


class MemoryObjectStore:
    """Thread-safe content store used by tests and ephemeral runtimes."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self._lock = RLock()

    def put(self, payload: bytes) -> tuple[str, bool]:
        value = bytes(payload)
        object_hash = _object_hash(value)
        with self._lock:
            inserted = object_hash not in self._objects
            if inserted:
                self._objects[object_hash] = value
        return object_hash, inserted

    def get(self, object_hash: str) -> bytes:
        with self._lock:
            try:
                return self._objects[object_hash]
            except KeyError as exc:
                raise KeyError("canonical object is unavailable: {}".format(object_hash)) from exc

    def batch(self):
        return contextlib.nullcontext()

    def delete_except(self, retained: set[str]) -> int:
        with self._lock:
            stale = [key for key in self._objects if key not in retained]
            for key in stale:
                del self._objects[key]
        return len(stale)

    def __len__(self) -> int:
        with self._lock:
            return len(self._objects)

    @property
    def byte_count(self) -> int:
        with self._lock:
            return sum(len(value) for value in self._objects.values())


class SQLiteObjectStore:
    """Private compressed object database for unsaved-session snapshots.

    SQLite avoids thousands of small filesystem objects. Each content object is
    inserted once, compressed, and committed in a short transaction on the MCP
    worker thread rather than the Glyphs drawing thread.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        self._lock = RLock()
        self._connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=DELETE")
        self._connection.execute("PRAGMA synchronous=NORMAL")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS objects ("
            "hash TEXT PRIMARY KEY, payload BLOB NOT NULL, raw_size INTEGER NOT NULL"
            ") WITHOUT ROWID"
        )
        self._connection.commit()
        self._batch_depth = 0
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def put(self, payload: bytes) -> tuple[str, bool]:
        value = bytes(payload)
        object_hash = _object_hash(value)
        packed = zlib.compress(value, level=3)
        with self._lock:
            cursor = self._connection.execute(
                "INSERT OR IGNORE INTO objects(hash, payload, raw_size) VALUES (?, ?, ?)",
                (object_hash, sqlite3.Binary(packed), len(value)),
            )
            if self._batch_depth == 0:
                self._connection.commit()
            inserted = bool(cursor.rowcount)
        return object_hash, inserted

    @contextlib.contextmanager
    def batch(self):
        self._lock.acquire()
        try:
            self._batch_depth += 1
            if self._batch_depth == 1:
                self._connection.execute("BEGIN")
            yield
        except Exception:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self._connection.rollback()
            raise
        else:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self._connection.commit()
        finally:
            self._lock.release()

    def get(self, object_hash: str) -> bytes:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM objects WHERE hash = ?", (object_hash,)
            ).fetchone()
        if row is None:
            raise KeyError("canonical object is unavailable: {}".format(object_hash))
        return zlib.decompress(bytes(row[0]))

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def delete_except(self, retained: set[str]) -> int:
        with self._lock:
            rows = self._connection.execute("SELECT hash FROM objects").fetchall()
            stale = [str(row[0]) for row in rows if str(row[0]) not in retained]
            self._connection.executemany("DELETE FROM objects WHERE hash = ?", ((key,) for key in stale))
            self._connection.commit()
        return len(stale)


@dataclass(frozen=True)
class TreeSnapshot:
    tree_hash: str
    model_fingerprint: str
    inserted_object_count: int
    inserted_byte_count: int
    glyph_count: int
    reused_glyph_count: int


class CanonicalFontTree:
    """Store complete models as small content-addressed tree objects.

    Glyph and kerning roots are maps of independently hashed entries. The root
    object therefore changes after an edit, while every unaffected entry hash is
    reused. Other domains stay as one blob until scale evidence justifies a
    finer shard.
    """

    def __init__(self, store: ObjectStore) -> None:
        self._store = store
        self._descriptor_cache: dict[str, Mapping[str, Any]] = {}
        self._lock = RLock()

    def _put_value(self, value: Any) -> tuple[str, bool, int]:
        payload = _json_bytes({"kind": "value", "value": value})
        object_hash, inserted = self._store.put(payload)
        return object_hash, inserted, len(payload) if inserted else 0

    def _put_descriptor(self, value: Mapping[str, Any]) -> tuple[str, bool, int]:
        payload = _json_bytes(value)
        object_hash, inserted = self._store.put(payload)
        if inserted:
            with self._lock:
                self._descriptor_cache[object_hash] = copy.deepcopy(dict(value))
        return object_hash, inserted, len(payload) if inserted else 0

    def store_model(self, model: Mapping[str, Any]) -> TreeSnapshot:
        batch = getattr(self._store, "batch", None)
        context = batch() if callable(batch) else contextlib.nullcontext()
        with context:
            return self._store_model(model)

    def _store_model(self, model: Mapping[str, Any]) -> TreeSnapshot:
        # canonical_json performs the authoritative JSON-safe normalization.
        encoded = canonical_json(model)
        plain = __import__("json").loads(encoded)
        model_fingerprint = _object_hash(encoded.encode("utf-8"))
        roots: dict[str, Any] = {}
        inserted_count = 0
        inserted_bytes = 0
        glyph_count = len(plain.get("glyphs") or {}) if isinstance(plain.get("glyphs"), Mapping) else 0
        reused_glyphs = 0

        for root_name in sorted(plain):
            root_value = plain[root_name]
            if root_name in SHARDED_MAPPING_ROOTS and isinstance(root_value, Mapping):
                entries: dict[str, str] = {}
                for key in sorted(root_value, key=str):
                    value_hash, inserted, byte_count = self._put_value(root_value[key])
                    entries[str(key)] = value_hash
                    inserted_count += int(inserted)
                    inserted_bytes += byte_count
                    if root_name == "glyphs" and not inserted:
                        reused_glyphs += 1
                map_descriptor = {
                    "kind": "map",
                    "schemaVersion": TREE_SCHEMA_VERSION,
                    "entries": entries,
                }
                map_hash, inserted, byte_count = self._put_descriptor(map_descriptor)
                inserted_count += int(inserted)
                inserted_bytes += byte_count
                roots[root_name] = {"kind": "map", "hash": map_hash}
            else:
                value_hash, inserted, byte_count = self._put_value(root_value)
                inserted_count += int(inserted)
                inserted_bytes += byte_count
                roots[root_name] = {"kind": "value", "hash": value_hash}

        root_descriptor = {
            "kind": "fontTree",
            "schemaVersion": TREE_SCHEMA_VERSION,
            "modelSchemaVersion": CANONICAL_MODEL_SCHEMA_VERSION,
            "reversibilityCoverage": REVERSIBILITY_COVERAGE,
            "modelFingerprint": model_fingerprint,
            "roots": roots,
        }
        tree_hash, inserted, byte_count = self._put_descriptor(root_descriptor)
        inserted_count += int(inserted)
        inserted_bytes += byte_count
        return TreeSnapshot(
            tree_hash=tree_hash,
            model_fingerprint=root_descriptor["modelFingerprint"],
            inserted_object_count=inserted_count,
            inserted_byte_count=inserted_bytes,
            glyph_count=glyph_count,
            reused_glyph_count=reused_glyphs,
        )

    def store_verified_transition(
        self,
        before_tree_hash: str,
        after_model: Mapping[str, Any],
        change_set: ChangeSet,
    ) -> TreeSnapshot:
        """Store one verified transition by rewriting changed canonical shards.

        The transaction kernel has already proved the complete after
        fingerprint. Reusing the before descriptor lets action history hash and
        persist only roots named by that semantic diff instead of serializing
        every unchanged glyph again.
        """

        before_descriptor = self.descriptor(before_tree_hash)
        if (
            str(before_descriptor.get("modelFingerprint") or "")
            != change_set.before_fingerprint
        ):
            raise ValueError("verified transition does not start at the supplied tree")
        glyphs = after_model.get("glyphs", {})
        glyph_count = len(glyphs) if isinstance(glyphs, Mapping) else 0
        if not change_set.changes:
            if change_set.before_fingerprint != change_set.after_fingerprint:
                raise ValueError("an empty verified transition cannot change fingerprints")
            return TreeSnapshot(
                tree_hash=before_tree_hash,
                model_fingerprint=change_set.after_fingerprint,
                inserted_object_count=0,
                inserted_byte_count=0,
                glyph_count=glyph_count,
                reused_glyph_count=glyph_count,
            )

        roots = copy.deepcopy(dict(before_descriptor.get("roots") or {}))
        changes_by_root: dict[str, list[Any]] = {}
        for change in change_set.changes:
            changes_by_root.setdefault(change.path[0], []).append(change)
        inserted_count = 0
        inserted_bytes = 0
        reused_glyphs = glyph_count

        batch = getattr(self._store, "batch", None)
        context = batch() if callable(batch) else contextlib.nullcontext()
        with context:
            for root_name, changes in sorted(changes_by_root.items()):
                root_value = after_model.get(root_name)
                if root_name in SHARDED_MAPPING_ROOTS and isinstance(
                    root_value, Mapping
                ):
                    previous_ref = roots.get(root_name)
                    if not isinstance(previous_ref, Mapping):
                        raise ValueError(
                            "verified transition is missing root {}".format(root_name)
                        )
                    previous_map = self._decode(str(previous_ref["hash"]))
                    entries = dict(previous_map.get("entries") or {})
                    changed_keys = {
                        change.path[1]
                        for change in changes
                        if len(change.path) >= 2
                    }
                    if any(len(change.path) < 2 for change in changes):
                        changed_keys = set(entries) | {
                            str(key) for key in root_value
                        }
                    expected_membership_delta = set(entries) ^ {
                        str(key) for key in root_value
                    }
                    if not expected_membership_delta.issubset(changed_keys):
                        raise ValueError(
                            "verified transition omitted a changed {} entry".format(
                                root_name
                            )
                        )
                    if root_name == "glyphs":
                        reused_glyphs = max(0, glyph_count - len(changed_keys))
                    for key in sorted(changed_keys):
                        if key not in root_value:
                            entries.pop(key, None)
                            continue
                        value_hash, inserted, byte_count = self._put_value(
                            root_value[key]
                        )
                        entries[str(key)] = value_hash
                        inserted_count += int(inserted)
                        inserted_bytes += byte_count
                        if root_name == "glyphs" and not inserted:
                            reused_glyphs += 1
                    map_descriptor = {
                        "kind": "map",
                        "schemaVersion": TREE_SCHEMA_VERSION,
                        "entries": entries,
                    }
                    map_hash, inserted, byte_count = self._put_descriptor(
                        map_descriptor
                    )
                    inserted_count += int(inserted)
                    inserted_bytes += byte_count
                    roots[root_name] = {"kind": "map", "hash": map_hash}
                else:
                    value_hash, inserted, byte_count = self._put_value(root_value)
                    inserted_count += int(inserted)
                    inserted_bytes += byte_count
                    roots[root_name] = {"kind": "value", "hash": value_hash}

            root_descriptor = {
                "kind": "fontTree",
                "schemaVersion": TREE_SCHEMA_VERSION,
                "modelSchemaVersion": CANONICAL_MODEL_SCHEMA_VERSION,
                "reversibilityCoverage": REVERSIBILITY_COVERAGE,
                "modelFingerprint": change_set.after_fingerprint,
                "roots": roots,
            }
            tree_hash, inserted, byte_count = self._put_descriptor(root_descriptor)
            inserted_count += int(inserted)
            inserted_bytes += byte_count

        return TreeSnapshot(
            tree_hash=tree_hash,
            model_fingerprint=change_set.after_fingerprint,
            inserted_object_count=inserted_count,
            inserted_byte_count=inserted_bytes,
            glyph_count=glyph_count,
            reused_glyph_count=reused_glyphs,
        )

    def _decode(self, object_hash: str) -> Mapping[str, Any]:
        with self._lock:
            cached = self._descriptor_cache.get(object_hash)
        if cached is not None:
            return copy.deepcopy(dict(cached))
        import json

        value = json.loads(self._store.get(object_hash).decode("utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("canonical object is not a mapping")
        return value

    def descriptor(self, tree_hash: str) -> Mapping[str, Any]:
        value = self._decode(tree_hash)
        if value.get("kind") != "fontTree" or value.get("schemaVersion") != TREE_SCHEMA_VERSION:
            raise ValueError("unsupported canonical font tree")
        return value

    def load_model(self, tree_hash: str) -> dict[str, Any]:
        descriptor = self.descriptor(tree_hash)
        model: dict[str, Any] = {}
        for root_name, root_ref in sorted((descriptor.get("roots") or {}).items()):
            child = self._decode(str(root_ref["hash"]))
            if child.get("kind") == "map":
                result: dict[str, Any] = {}
                for key, value_hash in sorted((child.get("entries") or {}).items()):
                    value = self._decode(str(value_hash))
                    result[str(key)] = copy.deepcopy(value.get("value"))
                model[str(root_name)] = result
            elif child.get("kind") == "value":
                model[str(root_name)] = copy.deepcopy(child.get("value"))
            else:
                raise ValueError("unsupported canonical root object")
        if fingerprint_model(model) != descriptor.get("modelFingerprint"):
            raise ValueError("canonical tree reconstruction failed fingerprint verification")
        return model

    def glyph(self, tree_hash: str, glyph_name: str) -> Any:
        descriptor = self.descriptor(tree_hash)
        glyphs_ref = (descriptor.get("roots") or {}).get("glyphs")
        if not glyphs_ref:
            return None
        glyph_map = self._decode(str(glyphs_ref["hash"]))
        value_hash = (glyph_map.get("entries") or {}).get(glyph_name)
        if not value_hash:
            return None
        return copy.deepcopy(self._decode(str(value_hash)).get("value"))

    def diff(self, before_tree_hash: str, after_tree_hash: str) -> ChangeSet:
        if before_tree_hash == after_tree_hash:
            model = self.load_model(before_tree_hash)
            return diff_models(model, model)
        return diff_models(self.load_model(before_tree_hash), self.load_model(after_tree_hash))

    def _reachable_from_tree(self, tree_hash: str) -> set[str]:
        retained = {tree_hash}
        descriptor = self.descriptor(tree_hash)
        for root_ref in (descriptor.get("roots") or {}).values():
            root_hash = str(root_ref["hash"])
            retained.add(root_hash)
            child = self._decode(root_hash)
            if child.get("kind") == "map":
                retained.update(str(value) for value in (child.get("entries") or {}).values())
        return retained

    def prune(self, retained_tree_hashes: set[str]) -> int:
        delete_except = getattr(self._store, "delete_except", None)
        if not callable(delete_except):
            return 0
        retained: set[str] = set()
        for tree_hash in retained_tree_hashes:
            retained.update(self._reachable_from_tree(tree_hash))
        deleted = int(delete_except(retained))
        with self._lock:
            self._descriptor_cache = {
                key: value for key, value in self._descriptor_cache.items() if key in retained
            }
        return deleted


__all__ = [
    "CANONICAL_MODEL_SCHEMA_VERSION",
    "CanonicalFontTree",
    "MemoryObjectStore",
    "ObjectStore",
    "REVERSIBILITY_COVERAGE",
    "SQLiteObjectStore",
    "SHARDED_MAPPING_ROOTS",
    "TREE_SCHEMA_VERSION",
    "TreeSnapshot",
]
