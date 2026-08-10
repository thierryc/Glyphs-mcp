from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path


RESOURCES = (
    Path(__file__).resolve().parent.parent
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
)
sys.path.insert(0, str(RESOURCES))

import outline_candidate_state as state  # noqa: E402


def _entry(entry_id="e1", node_count=1):
    return {
        "entryId": entry_id,
        "candidate": {
            "paths": [
                {
                    "closed": False,
                    "nodes": [
                        {"x": float(index), "y": 0.0, "type": "line", "smooth": False}
                        for index in range(node_count)
                    ],
                }
            ]
        },
    }


def _session(session_id="s1", entries=None):
    return {"sessionId": session_id, "operation": "tunni", "entries": entries or [_entry()]}


class CandidateStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = state.CandidateStore()

    def test_preview_state_is_detached_and_overlay_enabled(self):
        original = _session()
        stored = self.store.put_session(original)
        original["entries"][0]["candidate"]["paths"][0]["nodes"][0]["x"] = 999

        self.assertTrue(self.store.state()["enabled"])
        self.assertEqual(self.store.get_session("s1")["entries"][0]["candidate"]["paths"][0]["nodes"][0]["x"], 0.0)
        self.assertEqual(stored["candidateDataVersion"], 1)

    def test_oldest_session_is_evicted_deterministically(self):
        for index in range(state.MAX_SESSIONS + 1):
            self.store.put_session(_session("s{}".format(index), [_entry("e{}".format(index))]))

        self.assertIsNone(self.store.get_session("s0"))
        self.assertIsNotNone(self.store.get_session("s{}".format(state.MAX_SESSIONS)))
        self.assertEqual(self.store.state()["sessionCount"], state.MAX_SESSIONS)

    def test_entry_and_node_limits_reject_instead_of_truncating(self):
        with self.assertRaisesRegex(ValueError, "entry_limit"):
            self.store.put_session(
                _session("large", [_entry("e{}".format(index)) for index in range(state.MAX_ENTRIES + 1)])
            )
        with self.assertRaisesRegex(ValueError, "node_limit"):
            self.store.put_session(_session("nodes", [_entry("huge", state.MAX_TOTAL_NODES + 1)]))

    def test_ui_clear_never_implies_layer_deletion(self):
        self.store.put_session(_session())
        result = self.store.set_overlay(False, "s1", clear_session=True)

        self.assertEqual(result["clearedSessionId"], "s1")
        self.assertEqual(result["sessionCount"], 0)
        self.assertNotIn("deletedLayers", result)

    def test_tokens_are_one_time_bound_and_expire(self):
        token = self.store.issue_token("s1", {"e1": "source"}, {"e1": "candidate"})
        found, error = self.store.get_token(token["token"], "s1")
        self.assertIsNone(error)
        self.assertEqual(found["candidateFingerprints"]["e1"], "candidate")

        consumed, error = self.store.consume_token(token["token"], "s1")
        self.assertIsNone(error)
        self.assertIsNotNone(consumed)
        consumed_again, error = self.store.consume_token(token["token"], "s1")
        self.assertIsNone(consumed_again)
        self.assertEqual(error, "review_token_invalid_or_expired")

        expired = self.store.issue_token("s2", {}, {})
        self.store._tokens[expired["token"]]["expiresAt"] = time.time() - 1
        value, error = self.store.get_token(expired["token"], "s2")
        self.assertIsNone(value)
        self.assertEqual(error, "review_token_invalid_or_expired")


if __name__ == "__main__":
    unittest.main()
