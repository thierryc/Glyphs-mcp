"""Focused contracts for verified synchronous document saves."""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from jsonschema import validate


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.adapters.lifecycle import (  # noqa: E402
    GlyphsDocumentLifecycleObserver,
)
from glyphs_mcp_v2.application import GlyphsMCPApplication  # noqa: E402
from glyphs_mcp_v2.canonical_tree import CanonicalFontTree, MemoryObjectStore  # noqa: E402
from glyphs_mcp_v2.catalog import TOOL_CATALOG  # noqa: E402
from glyphs_mcp_v2.change_history import ChangeHistory  # noqa: E402
from glyphs_mcp_v2.change_lifecycle import DocumentHistoryLifecycle  # noqa: E402
from glyphs_mcp_v2.ports import FontSnapshot  # noqa: E402
from glyphs_mcp_v2.saving import DocumentSaveError  # noqa: E402
from glyphs_mcp_v2.semantic import fingerprint_model  # noqa: E402


def _model() -> dict:
    return {
        "font": {"familyName": "Save Test", "upm": 1000},
        "masters": [],
        "instances": [],
        "glyphs": {},
        "kerning": {},
        "features": [],
        "classes": [],
        "featurePrefixes": [],
    }


SOURCE_FINGERPRINT = "sha256:" + "1" * 64
SAVED_FINGERPRINT = "sha256:" + "2" * 64


class _SaveHost:
    def __init__(self) -> None:
        self.model = _model()
        self.source_state = {
            "kind": "glyphs",
            "exists": True,
            "readable": True,
            "contentFingerprint": SOURCE_FINGERPRINT,
        }
        self.save_calls = []
        self.reset_calls = []
        self.save_error = None
        self.result_overrides = {}

    def capture_model(self, document_id):
        return copy.deepcopy(self.model)

    def list_documents(self):
        return (
            FontSnapshot(
                document_id="doc_save",
                legacy_index=0,
                family_name="Save Test",
                file_path="/fonts/SaveTest.glyphs",
                has_unsaved_changes=True,
                active=True,
                master_count=0,
                instance_count=0,
                glyph_count=0,
                units_per_em=1000,
                version_major=1,
                version_minor=0,
                format_version=3,
                last_saved_app_version="4.0",
            ),
        )

    def capture_source_file_state(self, document_id):
        return copy.deepcopy(self.source_state)

    def reset_verified_change_tracking(self, document_id):
        self.reset_calls.append(document_id)

    def save_document(self, document_id, **arguments):
        self.save_calls.append((document_id, dict(arguments)))
        if self.save_error is not None:
            raise self.save_error
        destination = arguments.get("destination")
        save_as = bool(destination)
        result = {
            "saveMode": "save_as" if save_as else "save",
            "previousFilePath": "/fonts/SaveTest.glyphs",
            "filePath": destination or "/fonts/SaveTest.glyphs",
            "fileKind": "glyphspackage" if str(destination).endswith(".glyphspackage") else "glyphs",
            "overwritePolicy": arguments["overwrite_policy"],
            "previousSourceFingerprint": SOURCE_FINGERPRINT,
            "destinationBeforeFingerprint": None if save_as else SOURCE_FINGERPRINT,
            "savedSourceFingerprint": SAVED_FINGERPRINT,
            "replacedDestinationFingerprint": None,
            "dirtyBefore": True,
            "dirtyAfter": False,
            "pathChanged": save_as,
            "originalSourceUnchanged": True if save_as else None,
            "destinationChanged": True,
            "nativeSaveSucceeded": True,
            "savedModel": copy.deepcopy(self.model),
        }
        result.update(copy.deepcopy(self.result_overrides))
        return result


class SaveApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.host = _SaveHost()
        self.history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        self.app = GlyphsMCPApplication(self.host, history=self.history)

    def _arguments(self, **changes):
        arguments = {
            "documentId": "doc_save",
            "expectedDocumentFingerprint": fingerprint_model(self.host.model),
            "expectedSourceFingerprint": SOURCE_FINGERPRINT,
            "confirm": True,
            "reason": "Publish the reviewed source",
        }
        arguments.update(changes)
        return arguments

    def test_verified_save_is_one_call_resets_history_and_validates_schema(self):
        changed = _model()
        changed["font"]["familyName"] = "Earlier Tool Edit"
        self.history.record_action(
            document_id="doc_save",
            tool="edit",
            effect="edit",
            status="success",
            run_id="run_seed",
            before_model=_model(),
            after_model=changed,
        )

        response = self.app.invoke("save_document", self._arguments()).to_dict()

        self.assertTrue(response["ok"])
        self.assertEqual(response["effect"], "save")
        self.assertEqual(len(self.host.save_calls), 1)
        self.assertEqual(
            self.host.save_calls[0][1]["expected_document_fingerprint"],
            fingerprint_model(self.host.model),
        )
        self.assertEqual(self.history.list_commits("doc_save"), ())
        self.assertEqual(self.host.reset_calls, ["doc_save"])
        token = self.host.save_calls[0][1]["notification_correlation_token"]
        self.assertFalse(
            self.app.document_was_saved("doc_save", correlation_token=token)
        )
        self.assertEqual(self.host.reset_calls, ["doc_save"])
        self.assertFalse(response["data"]["historyRecorded"])
        self.assertNotIn(
            "history_not_recorded",
            {warning["code"] for warning in response["warnings"]},
        )
        self.assertEqual(
            self.app._audit.list_events(document_id="doc_save")[-1].details[
                "reason"
            ],
            "Publish the reviewed source",
        )
        validate(response, TOOL_CATALOG["save_document"].output_schema)

    def test_save_as_changes_the_normal_document_path_contract(self):
        response = self.app.invoke(
            "save_document",
            self._arguments(destination="/fonts/Renamed.glyphspackage"),
        ).to_dict()

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["saveMode"], "save_as")
        self.assertTrue(response["data"]["pathChanged"])
        self.assertTrue(response["data"]["originalSourceUnchanged"])

    def test_save_as_accepts_a_truthful_resolved_system_alias_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolved_parent = root / "resolved"
            resolved_parent.mkdir()
            alias_parent = root / "alias"
            alias_parent.symlink_to(resolved_parent, target_is_directory=True)
            requested = alias_parent / "Renamed.glyphs"
            observed = resolved_parent / "Renamed.glyphs"
            self.host.result_overrides = {"filePath": str(observed)}

            response = self.app.invoke(
                "save_document",
                self._arguments(destination=str(requested)),
            ).to_dict()

        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["filePath"], str(observed))

    def test_confirmation_and_nonblank_reason_are_preconditions(self):
        missing_confirmation = self.app.invoke(
            "save_document", self._arguments(confirm=False)
        ).to_dict()
        blank_reason = self.app.invoke(
            "save_document", self._arguments(reason="   ")
        ).to_dict()

        self.assertEqual(missing_confirmation["error"]["code"], "confirmation_required")
        self.assertEqual(blank_reason["error"]["code"], "invalid_request")
        self.assertEqual(self.host.save_calls, [])

    def test_typed_host_failure_is_audited_without_claiming_a_save(self):
        self.host.save_error = DocumentSaveError(
            "destination_exists",
            "The destination exists.",
            details={
                "destinationState": {
                    "kind": "glyphs",
                    "exists": True,
                    "readable": True,
                    "contentFingerprint": SOURCE_FINGERPRINT,
                }
            },
        )

        response = self.app.invoke(
            "save_document", self._arguments(destination="/fonts/Existing.glyphs")
        ).to_dict()

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "destination_exists")
        self.assertFalse(response["data"]["saveAttempted"])
        self.assertFalse(response["data"]["fontSaved"])

    def test_save_refusals_never_append_history_commits(self):
        changed = _model()
        changed["font"]["familyName"] = "Earlier Tool Edit"
        seed = self.history.record_action(
            document_id="doc_save",
            tool="edit",
            effect="edit",
            status="success",
            run_id="run_seed",
            before_model=_model(),
            after_model=changed,
        )
        before = tuple(
            commit.run_id for commit in self.history.list_commits("doc_save")
        )

        refused = self.app.invoke(
            "save_document", self._arguments(confirm=False)
        ).to_dict()
        self.host.save_error = DocumentSaveError(
            "stale_source_file", "The source changed."
        )
        failed = self.app.invoke("save_document", self._arguments()).to_dict()

        self.assertEqual(before, (seed.run_id,))
        self.assertEqual(
            tuple(
                commit.run_id
                for commit in self.history.list_commits("doc_save")
            ),
            before,
        )
        self.assertFalse(refused["data"]["historyRecorded"])
        self.assertFalse(failed["data"]["historyRecorded"])
        for response in (refused, failed):
            self.assertNotIn(
                "history_not_recorded",
                {warning["code"] for warning in response["warnings"]},
            )

    def test_application_rejects_incomplete_save_as_proof(self):
        for override in (
            {"originalSourceUnchanged": None},
            {"destinationChanged": False},
            {"filePath": "/fonts/Unexpected.glyphs"},
        ):
            with self.subTest(override=override):
                self.host.result_overrides = override
                response = self.app.invoke(
                    "save_document",
                    self._arguments(destination="/fonts/Renamed.glyphs"),
                ).to_dict()

                self.assertFalse(response["ok"])
                self.assertEqual(
                    response["error"]["code"], "save_verification_failed"
                )
                self.assertFalse(response["data"]["saveVerified"])
                self.assertEqual(self.host.reset_calls, [])
                # Failure correlation is pending by design; consume the exact
                # native notification before exercising the next subcase.
                token = self.host.save_calls[-1][1][
                    "notification_correlation_token"
                ]
                self.app.document_was_saved(
                    "doc_save", correlation_token=token
                )

class SaveLifecycleTests(unittest.TestCase):
    def test_tool_save_notification_defers_reset_until_verified_completion(self):
        history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        resets = []
        lifecycle = DocumentHistoryLifecycle(history, reset_tracking=resets.append)
        token = lifecycle.begin_tool_save("doc_save")

        self.assertFalse(
            lifecycle.document_was_saved("doc_save", correlation_token=token)
        )
        result = lifecycle.complete_tool_save("doc_save", token, verified=True)

        self.assertTrue(result["notificationObserved"])
        self.assertTrue(result["historyReset"])
        self.assertEqual(resets, ["doc_save"])

    def test_late_native_notification_is_suppressed_after_one_verified_reset(self):
        history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        resets = []
        lifecycle = DocumentHistoryLifecycle(history, reset_tracking=resets.append)
        token = lifecycle.begin_tool_save("doc_save")

        result = lifecycle.complete_tool_save(
            "doc_save", token, verified=True, expect_notification=True
        )
        late_reset = lifecycle.document_was_saved(
            "doc_save", correlation_token=token
        )

        self.assertTrue(result["historyReset"])
        self.assertFalse(result["notificationObserved"])
        self.assertFalse(late_reset)
        self.assertEqual(resets, ["doc_save"])

    def test_failed_tool_save_retains_history_and_tracking(self):
        history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        resets = []
        lifecycle = DocumentHistoryLifecycle(history, reset_tracking=resets.append)
        token = lifecycle.begin_tool_save("doc_save")
        lifecycle.document_was_saved("doc_save", correlation_token=token)

        result = lifecycle.complete_tool_save("doc_save", token, verified=False)

        self.assertFalse(result["historyReset"])
        self.assertEqual(resets, [])

    def test_cleanup_keeps_the_document_fenced_until_reset_finishes(self):
        history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        lifecycle = None
        nested_attempts = []

        def reset_tracking(document_id):
            try:
                lifecycle.begin_tool_save(document_id)
            except RuntimeError:
                nested_attempts.append("fenced")

        lifecycle = DocumentHistoryLifecycle(
            history, reset_tracking=reset_tracking
        )
        token = lifecycle.begin_tool_save("doc_save")

        result = lifecycle.complete_tool_save(
            "doc_save", token, verified=True
        )

        self.assertTrue(result["historyReset"])
        self.assertEqual(nested_attempts, ["fenced"])

    def test_pending_notification_requires_the_exact_correlation_token(self):
        history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        resets = []
        lifecycle = DocumentHistoryLifecycle(history, reset_tracking=resets.append)
        token = lifecycle.begin_tool_save("doc_save")
        lifecycle.complete_tool_save(
            "doc_save", token, verified=True, expect_notification=True
        )

        self.assertFalse(
            lifecycle.document_was_saved(
                "doc_save", correlation_token="save_stale"
            )
        )
        next_token = lifecycle.begin_tool_save("doc_save")
        self.assertFalse(
            lifecycle.document_was_saved(
                "doc_save", correlation_token=token
            )
        )
        lifecycle.complete_tool_save(
            "doc_save", next_token, verified=False, expect_notification=True
        )
        self.assertFalse(
            lifecycle.document_was_saved(
                "doc_save", correlation_token=next_token
            )
        )
        self.assertNotEqual(next_token, token)
        self.assertEqual(resets, ["doc_save"])

    def test_missing_failed_save_notification_does_not_lock_future_saves(self):
        history = ChangeHistory(CanonicalFontTree(MemoryObjectStore()))
        lifecycle = DocumentHistoryLifecycle(history)
        failed_token = lifecycle.begin_tool_save("doc_save")
        lifecycle.complete_tool_save(
            "doc_save",
            failed_token,
            verified=False,
            expect_notification=True,
        )

        next_token = lifecycle.begin_tool_save("doc_save")

        self.assertNotEqual(next_token, failed_token)


class LifecycleObserverTests(unittest.TestCase):
    def test_observer_forwards_identity_only_and_unregisters(self):
        callbacks = []
        removed = []
        glyphs = SimpleNamespace(
            addCallback=lambda callback, event: callbacks.append((callback, event)),
            removeCallback=removed.append,
        )
        font = SimpleNamespace(glyphs=[])
        host = SimpleNamespace(document_id_for_font=lambda value: "doc_save")
        saved = []
        closed = []
        application = SimpleNamespace(
            document_was_saved=saved.append,
            document_was_closed=closed.append,
        )
        observer = GlyphsDocumentLifecycleObserver(
            glyphs,
            host,
            application,
            saved_event="saved",
            closed_event="closed",
        )

        callbacks[0][0](font)
        callbacks[1][0](font)
        observer.close()

        self.assertEqual(saved, ["doc_save"])
        self.assertEqual(closed, ["doc_save"])
        self.assertEqual(len(removed), 2)


if __name__ == "__main__":
    unittest.main()
