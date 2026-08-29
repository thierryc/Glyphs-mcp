"""Host-boundary tests for the one-shot native save adapter."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))

from glyphs_mcp_v2.adapters import document as document_adapter  # noqa: E402
from glyphs_mcp_v2.adapters.document import GlyphsDocumentHost  # noqa: E402
from glyphs_mcp_v2.saving import DocumentSaveError  # noqa: E402


class _Immediate:
    def run(self, callback):
        return callback()


class _SaveDocument:
    def __init__(self, font) -> None:
        self.font = font
        self.changeCount = 0
        self.hasUnautosavedChanges = True
        self.isDocumentEdited = True
        self.calls = []
        self.update_path = True
        self.raise_after_write = None
        self.native_result = (True, None)
        self.saveDocument_ = mock.Mock(
            side_effect=AssertionError("copy/dialog save API must not be used")
        )

    def saveToURL_ofType_forSaveOperation_error_(
        self, url, type_name, operation, error
    ):
        self.calls.append((str(url), type_name, operation, error))
        target = Path(str(url))
        if target.suffix.lower() == ".glyphspackage":
            target.mkdir(exist_ok=True)
            (target / "fontinfo.plist").write_bytes(b"verified native save")
        else:
            target.write_bytes(b"verified native save")
        if self.update_path:
            self.font.filepath = str(target)
        self.hasUnautosavedChanges = False
        self.isDocumentEdited = False
        if self.raise_after_write is not None:
            raise self.raise_after_write
        return self.native_result


class _SaveFont:
    def __init__(self, path) -> None:
        self.familyName = "Native Save"
        self.filepath = str(path) if path is not None else None
        self.instances = []
        self.glyphs = []
        self.parent = _SaveDocument(self)
        self.save = mock.Mock(
            side_effect=AssertionError("GSFont.save must not be used")
        )
        self.copy = mock.Mock(
            side_effect=AssertionError("copy save must not be used")
        )


class _App:
    def __init__(self, font) -> None:
        self.font = font
        self.fonts = [font]
        self.documents = []


def _native_modules():
    foundation = ModuleType("Foundation")

    class NSURL:
        @staticmethod
        def fileURLWithPath_(path):
            return str(path)

    foundation.NSURL = NSURL
    appkit = ModuleType("AppKit")
    appkit.NSSaveOperation = 0
    appkit.NSSaveAsOperation = 1
    return {"Foundation": foundation, "AppKit": appkit}


class NativeSaveAdapterTests(unittest.TestCase):
    def _host(self, font):
        host = GlyphsDocumentHost(_App(font), executor=_Immediate())
        document_id = host.document_id_for_font(font)
        expected = "sha256:" + "a" * 64
        snapshot = SimpleNamespace(document_fingerprint=expected)
        capture = mock.Mock(return_value=snapshot)
        host._capture_cached_snapshot = capture
        host.capture_stable_snapshot = mock.Mock(
            side_effect=AssertionError("save must not use canonical settling")
        )
        return host, document_id, expected, capture

    def _saved_model_patch(self):
        return mock.patch.object(
            document_adapter,
            "_saved_source_canonical_model",
            return_value={"font": {"familyName": "Native Save"}, "glyphs": {}},
        )

    def test_current_save_uses_one_synchronous_native_selector_without_copy_or_settling(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve() / "Current.glyphs"
            source.write_bytes(b"before")
            font = _SaveFont(source)
            host, document_id, expected, capture = self._host(font)
            source_fingerprint = document_adapter._normalized_source_file_state(
                source
            )["contentFingerprint"]

            with mock.patch.dict(sys.modules, _native_modules()), self._saved_model_patch():
                result = host.save_document(
                    document_id,
                    expected_document_fingerprint=expected,
                    expected_source_file_fingerprint=source_fingerprint,
                )

            self.assertEqual(result["saveMode"], "save")
            self.assertEqual(result["filePath"], str(source))
            self.assertEqual(len(font.parent.calls), 1)
            self.assertEqual(font.parent.calls[0][2], 0)
            self.assertGreaterEqual(capture.call_count, 2)
            host.capture_stable_snapshot.assert_not_called()
            font.save.assert_not_called()
            font.copy.assert_not_called()
            font.parent.saveDocument_.assert_not_called()

    def test_save_as_changes_normal_path_once_and_preserves_original_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve() / "Original.glyphs"
            target = Path(directory).resolve() / "Renamed.glyphs"
            original_bytes = b"original source"
            source.write_bytes(original_bytes)
            font = _SaveFont(source)
            host, document_id, expected, _capture = self._host(font)
            source_fingerprint = document_adapter._normalized_source_file_state(
                source
            )["contentFingerprint"]

            with mock.patch.dict(sys.modules, _native_modules()), self._saved_model_patch():
                result = host.save_document(
                    document_id,
                    expected_document_fingerprint=expected,
                    destination=str(target),
                    expected_source_file_fingerprint=source_fingerprint,
                )

            self.assertEqual(result["saveMode"], "save_as")
            self.assertTrue(result["pathChanged"])
            self.assertTrue(result["originalSourceUnchanged"])
            self.assertEqual(source.read_bytes(), original_bytes)
            self.assertEqual(font.filepath, str(target))
            self.assertEqual(len(font.parent.calls), 1)
            self.assertEqual(font.parent.calls[0][2], 1)

    def test_save_as_supports_both_flat_and_package_format_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for source_suffix, target_suffix, expected_kind in (
                (".glyphs", ".glyphspackage", "glyphspackage"),
                (".glyphspackage", ".glyphs", "glyphs"),
            ):
                with self.subTest(source=source_suffix, target=target_suffix):
                    source = root / ("Source" + source_suffix)
                    target = root / ("Target" + target_suffix)
                    if source_suffix == ".glyphspackage":
                        source.mkdir()
                        (source / "fontinfo.plist").write_bytes(b"original")
                    else:
                        source.write_bytes(b"original")
                    font = _SaveFont(source)
                    host, document_id, expected, _capture = self._host(font)
                    source_fingerprint = document_adapter._normalized_source_file_state(
                        source
                    )["contentFingerprint"]

                    with mock.patch.dict(sys.modules, _native_modules()), self._saved_model_patch():
                        result = host.save_document(
                            document_id,
                            expected_document_fingerprint=expected,
                            destination=str(target),
                            expected_source_file_fingerprint=source_fingerprint,
                        )

                    self.assertEqual(result["fileKind"], expected_kind)
                    self.assertEqual(len(font.parent.calls), 1)
                    self.assertEqual(font.parent.calls[0][2], 1)

    def test_save_as_requires_original_fingerprint_and_pathless_forbids_one(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve() / "Original.glyphs"
            source.write_bytes(b"original")
            target = Path(directory).resolve() / "Target.glyphs"
            font = _SaveFont(source)
            host, document_id, expected, _capture = self._host(font)

            with self.assertRaises(DocumentSaveError) as missing:
                host.save_document(
                    document_id,
                    expected_document_fingerprint=expected,
                    destination=str(target),
                )
            self.assertEqual(missing.exception.code, "invalid_request")
            self.assertEqual(font.parent.calls, [])

            pathless = _SaveFont(None)
            pathless_host, pathless_id, pathless_expected, _capture = self._host(
                pathless
            )
            with self.assertRaises(DocumentSaveError) as forbidden:
                pathless_host.save_document(
                    pathless_id,
                    expected_document_fingerprint=pathless_expected,
                    destination=str(target),
                    expected_source_file_fingerprint="sha256:" + "b" * 64,
                )
            self.assertEqual(forbidden.exception.code, "invalid_request")
            self.assertEqual(pathless.parent.calls, [])

    def test_save_as_refuses_a_missing_supported_original_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            missing_source = root / "Missing.glyphs"
            target = root / "Target.glyphs"
            font = _SaveFont(missing_source)
            host, document_id, expected, _capture = self._host(font)

            with self.assertRaises(DocumentSaveError) as unavailable:
                host.save_document(
                    document_id,
                    expected_document_fingerprint=expected,
                    destination=str(target),
                    expected_source_file_fingerprint="sha256:" + "b" * 64,
                )

            self.assertEqual(
                unavailable.exception.code, "source_file_unavailable"
            )
            self.assertEqual(font.parent.calls, [])

    def test_adapter_rechecks_document_fingerprint_and_rejects_unknown_dirty_state(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve() / "Current.glyphs"
            source.write_bytes(b"before")
            font = _SaveFont(source)
            host, document_id, expected, capture = self._host(font)
            capture.return_value = SimpleNamespace(
                document_fingerprint="sha256:" + "c" * 64
            )
            with self.assertRaises(DocumentSaveError) as stale:
                host.save_document(
                    document_id,
                    expected_document_fingerprint=expected,
                    expected_source_file_fingerprint="sha256:" + "d" * 64,
                )
            self.assertEqual(stale.exception.code, "stale_document")
            self.assertEqual(font.parent.calls, [])

            capture.return_value = SimpleNamespace(document_fingerprint=expected)
            font.parent.hasUnautosavedChanges = None
            font.parent.isDocumentEdited = None
            with self.assertRaises(DocumentSaveError) as unknown:
                host.save_document(
                    document_id,
                    expected_document_fingerprint=expected,
                    expected_source_file_fingerprint="sha256:" + "d" * 64,
                )
            self.assertEqual(
                unknown.exception.code, "document_dirty_state_unavailable"
            )
            self.assertEqual(font.parent.calls, [])

    def test_post_write_path_failure_is_truthful_verification_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve() / "Original.glyphs"
            target = Path(directory).resolve() / "Target.glyphs"
            source.write_bytes(b"before")
            font = _SaveFont(source)
            font.parent.update_path = False
            host, document_id, expected, _capture = self._host(font)
            source_fingerprint = document_adapter._normalized_source_file_state(
                source
            )["contentFingerprint"]

            with mock.patch.dict(sys.modules, _native_modules()):
                with self.assertRaises(DocumentSaveError) as failed:
                    host.save_document(
                        document_id,
                        expected_document_fingerprint=expected,
                        destination=str(target),
                        expected_source_file_fingerprint=source_fingerprint,
                    )

            error = failed.exception
            self.assertEqual(error.code, "save_verification_failed")
            self.assertTrue(error.write_attempted)
            self.assertTrue(error.details["nativeSaveSucceeded"])
            self.assertEqual(error.details["observedFilePath"], str(source))
            self.assertFalse(error.details["dirtyAfter"])
            self.assertIn("destinationStateAfter", error.details)

    def test_native_selector_exception_after_write_reports_observed_state(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve() / "Current.glyphs"
            source.write_bytes(b"before")
            font = _SaveFont(source)
            font.parent.raise_after_write = RuntimeError("native callback failed")
            host, document_id, expected, _capture = self._host(font)
            source_fingerprint = document_adapter._normalized_source_file_state(
                source
            )["contentFingerprint"]

            with mock.patch.dict(sys.modules, _native_modules()):
                with self.assertRaises(DocumentSaveError) as failed:
                    host.save_document(
                        document_id,
                        expected_document_fingerprint=expected,
                        expected_source_file_fingerprint=source_fingerprint,
                        notification_correlation_token="save_exception",
                    )

            error = failed.exception
            self.assertEqual(error.code, "save_verification_failed")
            self.assertFalse(error.recoverable)
            self.assertTrue(error.write_attempted)
            self.assertFalse(error.details["nativeSaveSucceeded"])
            self.assertTrue(error.details["fontSaved"])
            self.assertEqual(error.details["observedFilePath"], str(source))
            self.assertFalse(error.details["dirtyAfter"])
            self.assertNotEqual(
                error.details["destinationStateBefore"],
                error.details["destinationStateAfter"],
            )

    def test_native_false_after_write_is_not_a_prewrite_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve() / "Current.glyphs"
            source.write_bytes(b"before")
            font = _SaveFont(source)
            font.parent.native_result = (False, None)
            host, document_id, expected, _capture = self._host(font)
            source_fingerprint = document_adapter._normalized_source_file_state(
                source
            )["contentFingerprint"]

            with mock.patch.dict(sys.modules, _native_modules()):
                with self.assertRaises(DocumentSaveError) as failed:
                    host.save_document(
                        document_id,
                        expected_document_fingerprint=expected,
                        expected_source_file_fingerprint=source_fingerprint,
                    )

            self.assertEqual(
                failed.exception.code, "save_verification_failed"
            )
            self.assertTrue(failed.exception.write_attempted)
            self.assertFalse(
                failed.exception.details["nativeSaveSucceeded"]
            )

    def test_replace_if_match_is_fingerprint_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "Original.glyphs"
            target = root / "Existing.glyphs"
            source.write_bytes(b"original")
            target.write_bytes(b"replace me")
            font = _SaveFont(source)
            host, document_id, expected, _capture = self._host(font)
            source_fingerprint = document_adapter._normalized_source_file_state(
                source
            )["contentFingerprint"]
            destination_fingerprint = document_adapter._normalized_source_file_state(
                target
            )["contentFingerprint"]

            with mock.patch.dict(sys.modules, _native_modules()), self._saved_model_patch():
                result = host.save_document(
                    document_id,
                    expected_document_fingerprint=expected,
                    destination=str(target),
                    expected_source_file_fingerprint=source_fingerprint,
                    overwrite_policy="replace_if_match",
                    expected_destination_file_fingerprint=destination_fingerprint,
                )

            self.assertEqual(
                result["replacedDestinationFingerprint"],
                destination_fingerprint,
            )
            self.assertTrue(result["destinationChanged"])

            other_target = root / "Other.glyphs"
            other_target.write_bytes(b"existing")
            other_font = _SaveFont(source)
            other_host, other_id, other_expected, _capture = self._host(other_font)
            with self.assertRaises(DocumentSaveError) as stale:
                other_host.save_document(
                    other_id,
                    expected_document_fingerprint=other_expected,
                    destination=str(other_target),
                    expected_source_file_fingerprint=source_fingerprint,
                    overwrite_policy="replace_if_match",
                    expected_destination_file_fingerprint="sha256:" + "f" * 64,
                )
            self.assertEqual(stale.exception.code, "stale_destination")
            self.assertEqual(other_font.parent.calls, [])

    def test_current_source_race_is_not_misreported_as_destination_race(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve() / "Current.glyphs"
            source.write_bytes(b"before")
            font = _SaveFont(source)
            host, document_id, expected, _capture = self._host(font)
            source_fingerprint = document_adapter._normalized_source_file_state(
                source
            )["contentFingerprint"]
            actual = document_adapter._normalized_source_file_state
            calls = 0

            def raced_state(path):
                nonlocal calls
                calls += 1
                if calls == 3:
                    source.write_bytes(b"raced")
                return actual(path)

            with mock.patch.object(
                document_adapter,
                "_normalized_source_file_state",
                side_effect=raced_state,
            ):
                with self.assertRaises(DocumentSaveError) as raced:
                    host.save_document(
                        document_id,
                        expected_document_fingerprint=expected,
                        expected_source_file_fingerprint=source_fingerprint,
                    )

            self.assertEqual(raced.exception.code, "stale_source_file")
            self.assertEqual(font.parent.calls, [])

    def test_final_main_thread_fence_rejects_new_open_destination_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "Original.glyphs"
            target = root / "Existing.glyphs"
            source.write_bytes(b"original")
            target.write_bytes(b"destination")
            font = _SaveFont(source)
            other = _SaveFont(target)

            class HookedExecutor:
                def __init__(self):
                    self.calls = 0
                    self.host = None

                def run(self, callback):
                    self.calls += 1
                    if self.calls == 3:
                        self.host._app.fonts.append(other)
                    return callback()

            executor = HookedExecutor()
            host = GlyphsDocumentHost(_App(font), executor=executor)
            executor.host = host
            document_id = host.document_id_for_font(font)
            expected = "sha256:" + "a" * 64
            host._capture_cached_snapshot = mock.Mock(
                return_value=SimpleNamespace(document_fingerprint=expected)
            )
            source_fingerprint = document_adapter._normalized_source_file_state(
                source
            )["contentFingerprint"]
            destination_fingerprint = document_adapter._normalized_source_file_state(
                target
            )["contentFingerprint"]

            with mock.patch.dict(sys.modules, _native_modules()):
                with self.assertRaises(DocumentSaveError) as occupied:
                    host.save_document(
                        document_id,
                        expected_document_fingerprint=expected,
                        destination=str(target),
                        expected_source_file_fingerprint=source_fingerprint,
                        overwrite_policy="replace_if_match",
                        expected_destination_file_fingerprint=destination_fingerprint,
                    )

            self.assertEqual(
                occupied.exception.code, "destination_open_in_glyphs"
            )
            self.assertEqual(font.parent.calls, [])

    def test_hard_link_destination_is_save_as_not_current_path_save(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "Original.glyphs"
            target = root / "HardLink.glyphs"
            source.write_bytes(b"original")
            os.link(source, target)
            font = _SaveFont(source)
            host, document_id, expected, _capture = self._host(font)
            source_fingerprint = document_adapter._normalized_source_file_state(
                source
            )["contentFingerprint"]
            destination_fingerprint = document_adapter._normalized_source_file_state(
                target
            )["contentFingerprint"]

            with mock.patch.dict(sys.modules, _native_modules()), self._saved_model_patch():
                result = host.save_document(
                    document_id,
                    expected_document_fingerprint=expected,
                    destination=str(target),
                    expected_source_file_fingerprint=source_fingerprint,
                    overwrite_policy="replace_if_match",
                    expected_destination_file_fingerprint=destination_fingerprint,
                )

            self.assertEqual(result["saveMode"], "save_as")
            self.assertEqual(font.parent.calls[0][2], 1)
            self.assertTrue(result["pathChanged"])
            self.assertFalse(result["originalSourceUnchanged"])

    def test_unreadable_post_write_source_is_a_truthful_verification_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory).resolve() / "Current.glyphs"
            source.write_bytes(b"before")
            font = _SaveFont(source)
            host, document_id, expected, _capture = self._host(font)
            source_fingerprint = document_adapter._normalized_source_file_state(
                source
            )["contentFingerprint"]
            actual = document_adapter._normalized_source_file_state

            def unreadable_after_write(path):
                state = dict(actual(path))
                if font.parent.hasUnautosavedChanges is False:
                    state["readable"] = False
                    state["contentFingerprint"] = None
                return state

            with mock.patch.dict(sys.modules, _native_modules()), mock.patch.object(
                document_adapter,
                "_normalized_source_file_state",
                side_effect=unreadable_after_write,
            ):
                with self.assertRaises(DocumentSaveError) as failed:
                    host.save_document(
                        document_id,
                        expected_document_fingerprint=expected,
                        expected_source_file_fingerprint=source_fingerprint,
                    )

            self.assertEqual(failed.exception.code, "save_verification_failed")
            self.assertTrue(failed.exception.write_attempted)
            self.assertFalse(
                failed.exception.details["destinationStateAfter"]["readable"]
            )

    def test_adapter_source_never_selects_copy_or_nssavetoperation(self):
        source = Path(document_adapter.__file__).read_text(encoding="utf-8")
        method_source = source[
            source.index("    def save_document(") : source.index(
                "    def force_document_dirty(",
                source.index("    def save_document("),
            )
        ]
        self.assertNotIn("NSSaveToOperation", method_source)
        self.assertNotIn("saveDocument_", method_source)
        self.assertNotIn("makeCopy", method_source)
        self.assertNotIn("capture_stable_snapshot", method_source)

    def test_destination_validation_rejects_links_packages_and_unwritable_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            real = root / "real"
            real.mkdir()
            linked = root / "linked"
            linked.symlink_to(real, target_is_directory=True)
            with self.assertRaises(DocumentSaveError):
                document_adapter._validated_save_destination(
                    str(linked / "Font.glyphs")
                )

            package = root / "Outer.glyphspackage"
            package.mkdir()
            with self.assertRaises(DocumentSaveError):
                document_adapter._validated_save_destination(
                    str(package / "Nested.glyphs")
                )

            with mock.patch.object(document_adapter.os, "access", return_value=False):
                with self.assertRaises(DocumentSaveError) as unwritable:
                    document_adapter._validated_save_destination(
                        str(real / "Font.glyphs")
                    )
            self.assertEqual(
                unwritable.exception.code, "destination_parent_unwritable"
            )

    @unittest.skipUnless(sys.platform == "darwin", "macOS root aliases only")
    def test_destination_validation_accepts_standard_var_root_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            resolved = Path(directory).resolve()
            if not str(resolved).startswith("/private/var/"):
                self.skipTest("temporary directory is not under /private/var")
            aliased = Path(str(resolved).replace("/private/var/", "/var/", 1))

            target = document_adapter._validated_save_destination(
                str(aliased / "Alias.glyphs")
            )

            self.assertEqual(target, resolved / "Alias.glyphs")


if __name__ == "__main__":
    unittest.main()
