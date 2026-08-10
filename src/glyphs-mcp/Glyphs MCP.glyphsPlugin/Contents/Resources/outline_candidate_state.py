# encoding: utf-8

from __future__ import division, print_function, unicode_literals

"""Bounded process-local state for detached outline candidate previews.

This module deliberately has no GlyphsApp or AppKit imports. Host wrappers own
all snapshots and mutations; Reporters only read detached dictionaries.
"""

import copy
import hashlib
import json
import threading
import time
import uuid
from collections import OrderedDict


CANDIDATE_DATA_VERSION = 1
MAX_SESSIONS = 16
MAX_ENTRIES = 256
MAX_TOTAL_NODES = 100000
MAX_REVIEW_TOKENS = 128
REVIEW_TOKEN_TTL_SECONDS = 300.0


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def short_id(value):
    return str(value or "")[:12]


def new_id(prefix):
    return "{}-{}".format(str(prefix), uuid.uuid4().hex)


def count_nodes(snapshot):
    return sum(len(path.get("nodes") or []) for path in (snapshot.get("paths") or []))


class CandidateStore(object):
    def __init__(self):
        self._lock = threading.RLock()
        self._sessions = OrderedDict()
        self._tokens = OrderedDict()
        self._active_session_id = None
        self._overlay_enabled = False
        self._redraw_callback = None

    def reset(self):
        with self._lock:
            self._sessions.clear()
            self._tokens.clear()
            self._active_session_id = None
            self._overlay_enabled = False
            self._redraw_callback = None

    def set_redraw_callback(self, callback):
        with self._lock:
            self._redraw_callback = callback if callable(callback) else None

    def request_redraw(self):
        with self._lock:
            callback = self._redraw_callback
        if callback:
            try:
                callback()
                return True
            except Exception:
                return False
        return False

    def _totals(self, excluding=None):
        sessions = [item for key, item in self._sessions.items() if key != excluding]
        return (
            sum(len(item.get("entries") or []) for item in sessions),
            sum(sum(count_nodes(entry.get("candidate") or {}) for entry in item.get("entries") or []) for item in sessions),
        )

    def put_session(self, session):
        value = copy.deepcopy(session)
        session_id = str(value.get("sessionId") or new_id("session"))
        value["sessionId"] = session_id
        value["candidateDataVersion"] = CANDIDATE_DATA_VERSION
        value["updatedAt"] = float(time.time())
        value.setdefault("createdAt", value["updatedAt"])
        entries = list(value.get("entries") or [])
        if not entries:
            raise ValueError("candidate_session_empty")
        for entry in entries:
            entry.setdefault("entryId", new_id("entry"))
        with self._lock:
            entry_total, node_total = self._totals(excluding=session_id)
            if len(entries) > MAX_ENTRIES or entry_total + len(entries) > MAX_ENTRIES:
                raise ValueError("candidate_entry_limit_exceeded")
            session_nodes = sum(count_nodes(entry.get("candidate") or {}) for entry in entries)
            if node_total + session_nodes > MAX_TOTAL_NODES:
                raise ValueError("candidate_node_limit_exceeded")
            if session_id in self._sessions:
                del self._sessions[session_id]
            self._sessions[session_id] = value
            while len(self._sessions) > MAX_SESSIONS:
                evicted_id, _evicted = self._sessions.popitem(last=False)
                self._tokens = OrderedDict(
                    (key, token) for key, token in self._tokens.items() if token.get("sessionId") != evicted_id
                )
            self._active_session_id = session_id
            self._overlay_enabled = True
        self.request_redraw()
        return copy.deepcopy(value)

    def get_session(self, session_id=None):
        with self._lock:
            resolved = str(session_id or self._active_session_id or "")
            value = self._sessions.get(resolved)
            if value is None:
                return None
            self._sessions.move_to_end(resolved)
            return copy.deepcopy(value)

    def sessions(self):
        with self._lock:
            return [copy.deepcopy(value) for value in self._sessions.values()]

    def update_session(self, session):
        session_id = str(session.get("sessionId") or "")
        if not session_id:
            raise ValueError("session_id_required")
        return self.put_session(session)

    def set_overlay(self, enabled, session_id=None, clear_session=False):
        with self._lock:
            if type(enabled) is not bool:
                raise ValueError("enabled_must_be_boolean")
            if session_id is not None and str(session_id) not in self._sessions:
                raise KeyError("candidate_session_not_found")
            if session_id is not None:
                self._active_session_id = str(session_id)
            self._overlay_enabled = enabled
            cleared = None
            if clear_session:
                cleared = str(session_id or self._active_session_id or "")
                if cleared:
                    self._sessions.pop(cleared, None)
                    self._tokens = OrderedDict(
                        (key, token) for key, token in self._tokens.items() if token.get("sessionId") != cleared
                    )
                self._active_session_id = next(reversed(self._sessions), None) if self._sessions else None
                if not self._sessions:
                    self._overlay_enabled = False
            state = self.state()
            state["clearedSessionId"] = cleared
        self.request_redraw()
        return state

    def state(self):
        with self._lock:
            entries, nodes = self._totals()
            return {
                "enabled": bool(self._overlay_enabled),
                "activeSessionId": self._active_session_id,
                "sessionCount": len(self._sessions),
                "entryCount": entries,
                "nodeCount": nodes,
                "limits": {
                    "sessions": MAX_SESSIONS,
                    "entries": MAX_ENTRIES,
                    "nodes": MAX_TOTAL_NODES,
                },
            }

    def matching_entry(self, font_key, glyph_name, layer_id):
        with self._lock:
            session_ids = list(self._sessions.keys())
            if self._active_session_id in session_ids:
                session_ids.remove(self._active_session_id)
                session_ids.append(self._active_session_id)
            for session_id in reversed(session_ids):
                session = self._sessions[session_id]
                for entry in session.get("entries") or []:
                    if (
                        str(entry.get("fontKey")) == str(font_key)
                        and str(entry.get("glyphName")) == str(glyph_name)
                        and str(entry.get("sourceLayerId")) == str(layer_id)
                    ):
                        return copy.deepcopy(session), copy.deepcopy(entry), False
                    if str(entry.get("materializedLayerId")) == str(layer_id):
                        return copy.deepcopy(session), copy.deepcopy(entry), True
            return None, None, False

    def issue_token(self, session_id, source_fingerprints, candidate_fingerprints):
        now = float(time.time())
        token_id = new_id("review")
        payload = {
            "token": token_id,
            "sessionId": str(session_id),
            "sourceFingerprints": copy.deepcopy(source_fingerprints),
            "candidateFingerprints": copy.deepcopy(candidate_fingerprints),
            "createdAt": now,
            "expiresAt": now + REVIEW_TOKEN_TTL_SECONDS,
        }
        with self._lock:
            self._purge_tokens(now)
            self._tokens[token_id] = payload
            while len(self._tokens) > MAX_REVIEW_TOKENS:
                self._tokens.popitem(last=False)
        return copy.deepcopy(payload)

    def _purge_tokens(self, now=None):
        now = float(time.time() if now is None else now)
        self._tokens = OrderedDict(
            (key, token) for key, token in self._tokens.items() if float(token.get("expiresAt", 0.0)) > now
        )

    def consume_token(self, token_id, session_id):
        with self._lock:
            self._purge_tokens()
            token = self._tokens.pop(str(token_id), None)
            if token is None:
                return None, "review_token_invalid_or_expired"
            if str(token.get("sessionId")) != str(session_id):
                return None, "review_token_session_mismatch"
            return copy.deepcopy(token), None

    def get_token(self, token_id, session_id):
        with self._lock:
            self._purge_tokens()
            token = self._tokens.get(str(token_id))
            if token is None:
                return None, "review_token_invalid_or_expired"
            if str(token.get("sessionId")) != str(session_id):
                return None, "review_token_session_mismatch"
            return copy.deepcopy(token), None


STORE = CandidateStore()
