"""Common v2 operation, pagination, audit, and document-state contracts."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.audit import AuditLog  # noqa: E402
from glyphs_mcp_v2.operations import OperationStore  # noqa: E402
from glyphs_mcp_v2.pagination import CursorError, paginate  # noqa: E402


class _Clock:
    def __init__(self) -> None:
        self.value = 1_700_000_000.0

    def __call__(self) -> float:
        return self.value


class V2CommonRuntimeTests(unittest.TestCase):
    def test_pagination_is_fingerprint_bound_and_capped(self) -> None:
        values = [{"name": "g{:03d}".format(index)} for index in range(225)]
        first = paginate(values, source_fingerprint="font_a", page_size=100)

        self.assertEqual(len(first.items), 100)
        self.assertEqual(first.page.page_size, 100)
        self.assertEqual(first.page.total_items, 225)
        self.assertIsNotNone(first.page.next_cursor)

        second = paginate(
            values,
            source_fingerprint="font_a",
            page_size=900,
            cursor=first.page.next_cursor,
        )
        self.assertEqual(len(second.items), 125)
        self.assertEqual(second.page.page_size, 500)

        with self.assertRaises(CursorError):
            paginate(
                values,
                source_fingerprint="font_changed",
                page_size=100,
                cursor=first.page.next_cursor,
            )

    def test_operation_store_consumes_reviews_and_expires_them(self) -> None:
        clock = _Clock()
        store = OperationStore(clock=clock, id_factory=lambda prefix: prefix + "fixed")
        review = store.create(kind="python_review", payload={"codeHash": "abc"}, ttl_seconds=900)

        self.assertEqual(store.get(review.operation_id).payload["codeHash"], "abc")
        self.assertEqual(store.consume(review.operation_id).operation_id, review.operation_id)
        self.assertIsNone(store.get(review.operation_id))

        expired = store.create(kind="review", payload={}, ttl_seconds=1)
        clock.value += 2
        self.assertIsNone(store.get(expired.operation_id))

    def test_audit_records_hashes_and_receipts_without_source_code(self) -> None:
        now = datetime(2026, 8, 16, 18, 0, tzinfo=timezone.utc)
        log = AuditLog(now=lambda: now, id_factory=lambda: "audit_fixed")
        receipt = log.record(
            tool="execute_python",
            effect="code",
            status="success",
            document_id="doc_alpha",
            details={"codeHash": "abc", "reason": "test", "code": "secret = 1"},
        )

        self.assertEqual(receipt.audit_id, "audit_fixed")
        event = log.list_events()[0].to_dict()
        self.assertEqual(event["details"]["codeHash"], "abc")
        self.assertNotIn("code", event["details"])
        self.assertNotIn("secret", repr(event))


if __name__ == "__main__":
    unittest.main()
