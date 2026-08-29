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
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Protocol

from .canonical_schema import CanonicalCoverage
from .canonical_views import semantic_identity_glyph
from .semantic import (
    _CACHED_FINGERPRINT_ACCESS,
    _persistent_set_at,
    _require_change_before,
    _value_at,
    ChangeSet,
    canonical_json,
    diff_models,
    fingerprint_model,
)


TREE_SCHEMA_VERSION = 1
CANONICAL_MODEL_SCHEMA_VERSION = 7
REVERSIBILITY_COVERAGE = "complete_semantic_state"
SHARDED_MAPPING_ROOTS = frozenset({"glyphs", "kerning"})


def _object_hash(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return canonical_json(value).encode("utf-8")


def _encoded_mapping_bytes(encodings: Mapping[str, bytes]) -> bytes:
    result = bytearray(b"{")
    for offset, key in enumerate(sorted(encodings, key=str)):
        if offset:
            result.extend(b",")
        result.extend(_json_bytes(str(key)))
        result.extend(b":")
        result.extend(encodings[key])
    result.extend(b"}")
    return bytes(result)


def _layer_encoding_items(
    layers: Any,
) -> tuple[str, tuple[tuple[str, Any], ...]]:
    if isinstance(layers, Mapping):
        return (
            "mapping",
            tuple((str(key), layers[key]) for key in sorted(layers, key=str)),
        )
    if isinstance(layers, (list, tuple)):
        counts: dict[str, int] = {}
        items = []
        for index, layer in enumerate(layers):
            identity = (
                str(layer.get("id") or "")
                if isinstance(layer, Mapping)
                else ""
            ) or "index:{}".format(index)
            occurrence = counts.get(identity, 0)
            counts[identity] = occurrence + 1
            key = identity if occurrence == 0 else "{}#{}".format(identity, occurrence)
            items.append((key, layer))
        return "sequence", tuple(items)
    return "scalar", ()


def _encoded_glyph_bytes(
    glyph: Mapping[str, Any],
    *,
    previous_glyph: Mapping[str, Any] | None = None,
    previous_layer_encodings: Mapping[str, bytes] | None = None,
) -> tuple[bytes, Mapping[str, bytes]]:
    """Encode one glyph while retaining every unchanged layer byte shard."""

    identity = semantic_identity_glyph(glyph)
    previous_identity = (
        semantic_identity_glyph(previous_glyph)
        if isinstance(previous_glyph, Mapping)
        else {}
    )
    fields: dict[str, bytes] = {}
    layer_encodings: dict[str, bytes] = {}
    for name, value in identity.items():
        key = str(name)
        if key != "layers":
            fields[key] = _json_bytes(value)
            continue
        kind, items = _layer_encoding_items(value)
        previous_kind, previous_items = _layer_encoding_items(
            previous_identity.get("layers")
        )
        previous_values = dict(previous_items) if kind == previous_kind else {}
        previous_encodings = dict(previous_layer_encodings or {})
        ordered: list[bytes] = []
        for layer_id, layer in items:
            previous_layer = previous_values.get(layer_id)
            encoded = previous_encodings.get(layer_id)
            if encoded is None or not (
                layer is previous_layer or layer == previous_layer
            ):
                encoded = _json_bytes(layer)
            layer_encodings[layer_id] = encoded
            ordered.append(encoded)
        if kind == "mapping":
            fields[key] = _encoded_mapping_bytes(layer_encodings)
        elif kind == "sequence":
            fields[key] = b"[" + b",".join(ordered) + b"]"
        else:
            fields[key] = _json_bytes(value)
    return _encoded_mapping_bytes(fields), _ImmutableMapping(layer_encodings)


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


def _snapshot_shard_hash(value: Any) -> str:
    return _object_hash(_json_bytes(value))


def _snapshot_encoded_hash(payload: bytes) -> str:
    return _object_hash(payload)


def _update_encoded_mapping_hash(
    digest: "hashlib._Hash", encodings: Mapping[str, bytes]
) -> None:
    """Feed one canonical JSON mapping into an existing SHA-256 digest.

    Values are already normalized canonical JSON shards. Joining those shards
    with the same sorted-key punctuation as :func:`canonical_json` produces
    exactly the historical whole-document byte stream without allocating or
    traversing that complete stream again.
    """

    digest.update(b"{")
    for offset, key in enumerate(sorted(encodings, key=str)):
        if offset:
            digest.update(b",")
        digest.update(_json_bytes(str(key)))
        digest.update(b":")
        digest.update(encodings[key])
    digest.update(b"}")


def _streamed_document_fingerprint(
    root_encodings: Mapping[str, bytes], glyph_encodings: Mapping[str, bytes]
) -> str:
    """Return the exact canonical document SHA from immutable shard bytes."""

    digest = hashlib.sha256()
    names = sorted((*root_encodings.keys(), "glyphs"), key=str)
    digest.update(b"{")
    for offset, name in enumerate(names):
        if offset:
            digest.update(b",")
        digest.update(_json_bytes(str(name)))
        digest.update(b":")
        if name == "glyphs":
            _update_encoded_mapping_hash(digest, glyph_encodings)
        else:
            digest.update(root_encodings[name])
    digest.update(b"}")
    return "sha256:" + digest.hexdigest()


def _snapshot_content_hash(root_hashes: Mapping[str, str]) -> str:
    return _object_hash(
        _json_bytes(
            {
                "modelSchemaVersion": CANONICAL_MODEL_SCHEMA_VERSION,
                "roots": dict(root_hashes),
            }
        )
    )


class _ImmutableMapping(Mapping[str, Any]):
    """Small read-only mapping whose explicit deepcopy is a plain boundary."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values = dict(values)

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, Any]:
        return copy.deepcopy(self._values, memo)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Mapping) and dict(self) == dict(other)


@dataclass(frozen=True)
class CanonicalSnapshot(Mapping[str, Any]):
    """Immutable canonical model view with reusable content shards.

    The public document fingerprint remains the schema-v7 canonical JSON
    fingerprint. ``content_tree_hash`` is an internal Merkle-style identity
    used to share unchanged roots and glyph entities without serializing them
    again. Native revision evidence is opaque to the core and never contributes
    to either identity.
    """

    model_schema_version: int
    content_tree_hash: str
    document_fingerprint: str
    root_shards: Mapping[str, Any]
    glyph_shards: Mapping[str, Any]
    root_hashes: Mapping[str, str]
    glyph_hashes: Mapping[str, str]
    root_encodings: Mapping[str, bytes]
    glyph_encodings: Mapping[str, bytes]
    glyph_layer_encodings: Mapping[str, Mapping[str, bytes]]
    native_revision_evidence: Mapping[str, Any]
    coverage: CanonicalCoverage = CanonicalCoverage.complete()
    reused_glyph_count: int = 0

    @classmethod
    def from_model(
        cls,
        model: Mapping[str, Any],
        *,
        native_revision_evidence: Mapping[str, Any] | None = None,
        coverage: CanonicalCoverage | None = None,
    ) -> "CanonicalSnapshot":
        import json

        encoded = canonical_json(model)
        plain = json.loads(encoded)
        return cls.from_shards(
            {
                str(name): value
                for name, value in plain.items()
                if str(name) != "glyphs"
            },
            dict(plain.get("glyphs") or {}),
            native_revision_evidence=native_revision_evidence,
            coverage=coverage,
        )

    @classmethod
    def from_shards(
        cls,
        root_shards: Mapping[str, Any],
        glyph_shards: Mapping[str, Any],
        *,
        previous: "CanonicalSnapshot | None" = None,
        document_fingerprint: str | None = None,
        native_revision_evidence: Mapping[str, Any] | None = None,
        coverage: CanonicalCoverage | None = None,
    ) -> "CanonicalSnapshot":
        """Assemble a snapshot while retaining equal previous shard objects."""

        roots: dict[str, Any] = {}
        root_hashes: dict[str, str] = {}
        root_encodings: dict[str, bytes] = {}
        for name, candidate in root_shards.items():
            key = str(name)
            previous_value = (
                previous.root_shards.get(key) if previous is not None else None
            )
            if (
                previous is not None
                and key in previous.root_shards
                and candidate == previous_value
            ):
                roots[key] = previous_value
                root_hashes[key] = previous.root_hashes[key]
                root_encodings[key] = previous.root_encodings[key]
            else:
                encoded = _json_bytes(candidate)
                roots[key] = candidate
                root_hashes[key] = _snapshot_encoded_hash(encoded)
                root_encodings[key] = encoded

        glyphs: dict[str, Any] = {}
        glyph_hashes: dict[str, str] = {}
        glyph_encodings: dict[str, bytes] = {}
        glyph_layer_encodings: dict[str, Mapping[str, bytes]] = {}
        reused = 0
        for name, candidate in glyph_shards.items():
            key = str(name)
            previous_value = (
                previous.glyph_shards.get(key) if previous is not None else None
            )
            if (
                previous is not None
                and key in previous.glyph_shards
                and candidate == previous_value
            ):
                glyphs[key] = previous_value
                glyph_hashes[key] = previous.glyph_hashes[key]
                glyph_encodings[key] = previous.glyph_encodings[key]
                glyph_layer_encodings[key] = previous.glyph_layer_encodings[key]
                reused += 1
            else:
                encoded, layer_encodings = _encoded_glyph_bytes(
                    candidate,
                    previous_glyph=previous_value
                    if isinstance(previous_value, Mapping)
                    else None,
                    previous_layer_encodings=(
                        previous.glyph_layer_encodings.get(key, {})
                        if previous is not None
                        else None
                    ),
                )
                glyphs[key] = candidate
                glyph_hashes[key] = _snapshot_encoded_hash(encoded)
                glyph_encodings[key] = encoded
                glyph_layer_encodings[key] = layer_encodings
        glyph_root_unchanged = bool(
            previous is not None
            and set(glyphs) == set(previous.glyph_shards)
            and reused == len(glyphs)
        )
        root_hashes["glyphs"] = (
            previous.root_hashes["glyphs"]
            if glyph_root_unchanged
            else _snapshot_shard_hash(glyph_hashes)
        )
        unchanged_from_previous = bool(
            previous is not None
            and set(roots) == set(previous.root_shards)
            and set(glyphs) == set(previous.glyph_shards)
            and all(
                roots[name] is previous.root_shards[name] for name in roots
            )
            and reused == len(glyphs)
        )
        computed_fingerprint = (
            previous.document_fingerprint
            if unchanged_from_previous
            else _streamed_document_fingerprint(root_encodings, glyph_encodings)
        )
        if (
            document_fingerprint is not None
            and document_fingerprint != computed_fingerprint
        ):
            raise ValueError("supplied document fingerprint does not match its shards")
        document_fingerprint = computed_fingerprint
        return cls(
            model_schema_version=CANONICAL_MODEL_SCHEMA_VERSION,
            content_tree_hash=_snapshot_content_hash(root_hashes),
            document_fingerprint=document_fingerprint,
            root_shards=_ImmutableMapping(roots),
            glyph_shards=_ImmutableMapping(glyphs),
            root_hashes=_ImmutableMapping(root_hashes),
            glyph_hashes=_ImmutableMapping(glyph_hashes),
            root_encodings=_ImmutableMapping(root_encodings),
            glyph_encodings=_ImmutableMapping(glyph_encodings),
            glyph_layer_encodings=_ImmutableMapping(glyph_layer_encodings),
            native_revision_evidence=_ImmutableMapping(
                copy.deepcopy(dict(native_revision_evidence or {}))
            ),
            coverage=coverage or (
                previous.coverage if previous is not None else CanonicalCoverage.complete()
            ),
            reused_glyph_count=reused,
        )

    def __getitem__(self, key: str) -> Any:
        if key == "glyphs":
            return self.glyph_shards
        return self.root_shards[key]

    def _verified_canonical_fingerprint(self, access: object) -> str | None:
        return (
            self.document_fingerprint
            if access is _CACHED_FINGERPRINT_ACCESS
            else None
        )

    def __iter__(self) -> Iterator[str]:
        return iter(sorted((*self.root_shards.keys(), "glyphs")))

    def __len__(self) -> int:
        return len(self.root_shards) + 1

    def materialize(self) -> dict[str, Any]:
        result = {
            name: copy.deepcopy(value) for name, value in self.root_shards.items()
        }
        result["glyphs"] = {
            name: copy.deepcopy(value) for name, value in self.glyph_shards.items()
        }
        return result

    def _rebase_shared_model(
        self, model: Mapping[str, Any]
    ) -> "CanonicalSnapshot":
        """Normalize one copy-on-write model while reusing unchanged shards.

        Mutation builders and native read-back both use this seam. It is
        intentionally domain-neutral: shard ownership, not the mutation tool,
        determines what must be encoded.
        """

        if model is self:
            return self
        glyphs = model.get("glyphs", {})
        if not isinstance(glyphs, Mapping):
            raise ValueError("canonical glyph root must be a mapping")
        return type(self).from_shards(
            {
                str(name): value
                for name, value in model.items()
                if str(name) != "glyphs"
            },
            {str(name): value for name, value in glyphs.items()},
            previous=self,
            coverage=self.coverage,
        )

    def _apply_verified_change_set(
        self, change_set: ChangeSet, *, verify_before: bool = True
    ) -> "CanonicalSnapshot":
        """Apply an already verified semantic patch without rebuilding JSON.

        ``diff_models`` and the lifecycle builders prove the exact public
        after-fingerprint when they create a change set. At runtime this method
        revalidates every before-value, applies the patch copy-on-write, and
        retains the declared exact fingerprint while hashing only changed
        shards. It is the immutable-snapshot equivalent of applying a Git
        tree delta.
        """

        if verify_before and self.document_fingerprint != change_set.before_fingerprint:
            raise ValueError("change set does not match the supplied before state")
        result: Mapping[str, Any] = self
        for change in sorted(
            change_set.changes,
            key=lambda item: (item.path[-1] == "$order", item.path),
        ):
            if verify_before:
                _require_change_before(_value_at(result, change.path), change)
            result = _persistent_set_at(
                result,
                change.path,
                change.after,
                change.after_present,
            )
        return self.store_verified_transition(result, change_set)

    def store_verified_transition(
        self,
        after_model: Mapping[str, Any],
        change_set: ChangeSet,
        *,
        native_revision_evidence: Mapping[str, Any] | None = None,
    ) -> "CanonicalSnapshot":
        """Create the proven after-snapshot by replacing changed shards only."""

        if change_set.before_fingerprint != self.document_fingerprint:
            raise ValueError("verified transition starts at another snapshot")
        if not change_set.changes:
            if change_set.after_fingerprint != self.document_fingerprint:
                raise ValueError("an empty transition cannot change fingerprints")
            return self

        changed_roots = {change.path[0] for change in change_set.changes}
        roots = dict(self.root_shards)
        root_hashes = dict(self.root_hashes)
        root_encodings = dict(self.root_encodings)
        glyphs = dict(self.glyph_shards)
        glyph_hashes = dict(self.glyph_hashes)
        glyph_encodings = dict(self.glyph_encodings)
        glyph_layer_encodings = dict(self.glyph_layer_encodings)
        after_glyphs = after_model.get("glyphs", {})
        if not isinstance(after_glyphs, Mapping):
            raise ValueError("canonical glyph root must be a mapping")
        changed_glyphs = {
            str(change.path[1])
            for change in change_set.changes
            if len(change.path) >= 2 and change.path[0] == "glyphs"
        }
        membership_delta = set(glyphs) ^ {str(name) for name in after_glyphs}
        if not membership_delta.issubset(changed_glyphs):
            raise ValueError("verified transition omitted changed glyph membership")
        glyph_changes: dict[str, list[Any]] = {}
        for change in change_set.changes:
            if len(change.path) >= 2 and change.path[0] == "glyphs":
                glyph_changes.setdefault(str(change.path[1]), []).append(change)
        for name in changed_glyphs:
            if name not in after_glyphs:
                glyphs.pop(name, None)
                glyph_hashes.pop(name, None)
                glyph_encodings.pop(name, None)
                glyph_layer_encodings.pop(name, None)
                continue
            exact = next(
                (
                    change
                    for change in glyph_changes.get(name, ())
                    if len(change.path) == 2
                ),
                None,
            )
            if exact is not None or name not in glyphs:
                value = after_glyphs[name]
            else:
                # Reapply the already verified nested patch through the same
                # copy-on-write primitive used by composition. This preserves
                # object identity for every sibling layer shard in a changed
                # glyph rather than replacing the complete glyph dictionary.
                value = glyphs[name]
                for change in sorted(
                    glyph_changes.get(name, ()),
                    key=lambda item: (item.path[-1] == "$order", item.path),
                ):
                    value = _persistent_set_at(
                        value,
                        change.path[2:],
                        change.after,
                        change.after_present,
                    )
                if value != after_glyphs[name]:
                    raise ValueError(
                        "verified transition omitted or misapplied a glyph fragment"
                    )
            glyphs[name] = value
            encoded, layer_encodings = _encoded_glyph_bytes(
                value,
                previous_glyph=self.glyph_shards.get(name),
                previous_layer_encodings=self.glyph_layer_encodings.get(name, {}),
            )
            glyph_encodings[name] = encoded
            glyph_hashes[name] = _snapshot_encoded_hash(encoded)
            glyph_layer_encodings[name] = layer_encodings
        if "glyphs" in changed_roots:
            root_hashes["glyphs"] = _snapshot_shard_hash(glyph_hashes)

        for root_name in changed_roots - {"glyphs"}:
            if root_name not in after_model:
                roots.pop(root_name, None)
                root_encodings.pop(root_name, None)
                root_hashes.pop(root_name, None)
                continue
            value = after_model.get(root_name)
            roots[root_name] = value
            encoded = _json_bytes(value)
            root_encodings[root_name] = encoded
            root_hashes[root_name] = _snapshot_encoded_hash(encoded)

        computed_fingerprint = _streamed_document_fingerprint(
            root_encodings, glyph_encodings
        )
        if computed_fingerprint != change_set.after_fingerprint:
            raise ValueError(
                "verified transition does not reproduce its after fingerprint"
            )

        return CanonicalSnapshot(
            model_schema_version=self.model_schema_version,
            content_tree_hash=_snapshot_content_hash(root_hashes),
            document_fingerprint=computed_fingerprint,
            root_shards=_ImmutableMapping(roots),
            glyph_shards=_ImmutableMapping(glyphs),
            root_hashes=_ImmutableMapping(root_hashes),
            glyph_hashes=_ImmutableMapping(glyph_hashes),
            root_encodings=_ImmutableMapping(root_encodings),
            glyph_encodings=_ImmutableMapping(glyph_encodings),
            glyph_layer_encodings=_ImmutableMapping(glyph_layer_encodings),
            native_revision_evidence=_ImmutableMapping(
                copy.deepcopy(
                    dict(
                        self.native_revision_evidence
                        if native_revision_evidence is None
                        else native_revision_evidence
                    )
                )
            ),
            coverage=self.coverage,
            reused_glyph_count=max(0, len(glyphs) - len(changed_glyphs)),
        )


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
        if isinstance(model, CanonicalSnapshot):
            # The live adapter has already normalized and fingerprinted these
            # immutable shards. Persist them independently instead of encoding
            # the complete font once here and then encoding every shard again.
            roots: dict[str, Any] = dict(model.root_shards)
            roots["glyphs"] = model.glyph_shards
            return self._store_roots(
                roots,
                model_fingerprint=model.document_fingerprint,
                coverage=model.coverage,
            )
        # canonical_json performs the authoritative JSON-safe normalization.
        encoded = canonical_json(model)
        plain = __import__("json").loads(encoded)
        return self._store_roots(
            plain,
            model_fingerprint=fingerprint_model(plain),
            coverage=CanonicalCoverage.complete(),
        )

    def _store_roots(
        self,
        model: Mapping[str, Any],
        *,
        model_fingerprint: str,
        coverage: CanonicalCoverage,
    ) -> TreeSnapshot:
        """Persist normalized canonical roots through one shared shard writer."""

        roots: dict[str, Any] = {}
        inserted_count = 0
        inserted_bytes = 0
        glyph_count = (
            len(model.get("glyphs") or {})
            if isinstance(model.get("glyphs"), Mapping)
            else 0
        )
        reused_glyphs = 0

        for root_name in sorted(model):
            root_value = model[root_name]
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
            "canonicalCoverage": coverage.to_public_dict(),
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
                if root_name not in after_model:
                    roots.pop(root_name, None)
                    continue
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
                "canonicalCoverage": CanonicalCoverage.complete().to_public_dict(),
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
            fingerprint = str(
                self.descriptor(before_tree_hash).get("modelFingerprint") or ""
            )
            return ChangeSet.from_changes(
                before_fingerprint=fingerprint,
                after_fingerprint=fingerprint,
                changes=(),
            )
        before_descriptor = self.descriptor(before_tree_hash)
        after_descriptor = self.descriptor(after_tree_hash)
        before_roots = before_descriptor.get("roots") or {}
        after_roots = after_descriptor.get("roots") or {}
        changes: list[Any] = []
        for root_name in sorted(set(before_roots) | set(after_roots)):
            before_ref = before_roots.get(root_name)
            after_ref = after_roots.get(root_name)
            if before_ref == after_ref:
                continue
            before_child = (
                self._decode(str(before_ref["hash"]))
                if isinstance(before_ref, Mapping)
                else None
            )
            after_child = (
                self._decode(str(after_ref["hash"]))
                if isinstance(after_ref, Mapping)
                else None
            )
            if (
                isinstance(before_child, Mapping)
                and isinstance(after_child, Mapping)
                and before_child.get("kind") == "map"
                and after_child.get("kind") == "map"
            ):
                before_entries = before_child.get("entries") or {}
                after_entries = after_child.get("entries") or {}
                for key in sorted(set(before_entries) | set(after_entries)):
                    if before_entries.get(key) == after_entries.get(key):
                        continue
                    before_fragment: dict[str, Any] = {str(root_name): {}}
                    after_fragment: dict[str, Any] = {str(root_name): {}}
                    if key in before_entries:
                        before_fragment[str(root_name)][str(key)] = self._decode(
                            str(before_entries[key])
                        ).get("value")
                    if key in after_entries:
                        after_fragment[str(root_name)][str(key)] = self._decode(
                            str(after_entries[key])
                        ).get("value")
                    changes.extend(
                        diff_models(before_fragment, after_fragment).changes
                    )
                continue
            before_value = (
                before_child.get("value")
                if isinstance(before_child, Mapping)
                else None
            )
            after_value = (
                after_child.get("value")
                if isinstance(after_child, Mapping)
                else None
            )
            changes.extend(
                diff_models(
                    ({str(root_name): before_value} if before_ref else {}),
                    ({str(root_name): after_value} if after_ref else {}),
                ).changes
            )
        return ChangeSet.from_changes(
            before_fingerprint=str(before_descriptor.get("modelFingerprint") or ""),
            after_fingerprint=str(after_descriptor.get("modelFingerprint") or ""),
            changes=changes,
        )

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
    "CanonicalSnapshot",
    "CanonicalFontTree",
    "MemoryObjectStore",
    "ObjectStore",
    "REVERSIBILITY_COVERAGE",
    "SQLiteObjectStore",
    "SHARDED_MAPPING_ROOTS",
    "TREE_SCHEMA_VERSION",
    "TreeSnapshot",
]
