"""Fail-closed contract tests for Glyphs 4 native-export evidence."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "src" / "glyphs-mcp" / "tests" / "fixtures" / "glyphs4-native-export-parity.json"
VALIDATOR_PATH = REPO / "scripts" / "validate_glyphs4_native_parity.py"
CAPTURE_PATH = REPO / "scripts" / "capture_glyphs4_native_export_parity.py"
V2_SOURCE = REPO / "src" / "glyphs-mcp-v2"
if str(V2_SOURCE) not in sys.path:
    sys.path.insert(0, str(V2_SOURCE))


def _load_validator():
    spec = importlib.util.spec_from_file_location("glyphs4_native_parity_validator", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_capture():
    spec = importlib.util.spec_from_file_location("glyphs4_native_parity_capture", CAPTURE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()
CAPTURE = _load_capture()


def _json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _pending_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _captured_fixture(root: Path) -> tuple[Path, dict]:
    payload = _pending_fixture()
    payload["captureStatus"] = "captured"
    payload["blocker"] = None
    payload["artifactRoot"] = "glyphs4-native-export-parity-artifacts"
    artifact_root = root / payload["artifactRoot"]
    artifact_root.mkdir()
    evidence = b"synthetic validator unit-test artifact\n"
    evidence_path = artifact_root / "native-observations.json"
    evidence_path.write_bytes(evidence)
    payload["artifacts"] = [
        {
            "byteSize": len(evidence),
            "relativePath": "native-observations.json",
            "sha256": hashlib.sha256(evidence).hexdigest(),
        }
    ]
    observations = {
        "rtl_class_orientation": {
            "compiledGpos": {"feature": "kern", "matches": [{"lookupIndex": 0}]},
            "nativeInput": {"direction": "rtl", "value": -73},
            "nativeStorage": {"master": {"first": {"second": -73}}},
            "ufoGroups": {"public.kern1.rtl": ["alef-ar"], "public.kern2.rtl": ["beh-ar"]},
            "ufoKerning": [{"first": "public.kern1.rtl", "second": "public.kern2.rtl", "value": -73}],
        },
        "vertical_sign_yadvance": {
            "compiledGpos": {"feature": "vkrn", "xAdvance": 0, "yAdvance": -61},
            "harfbuzz": {"vkrnOff": [{"ya": -1000}], "vkrnOn": [{"ya": -1061}]},
            "nativeInput": {"direction": "vertical", "value": -61},
        },
        "contextual_boundary_semantics": {
            "compiledGpos": {"features": [{"tag": "kern"}], "lookupTypes": [8, 1]},
            "harfbuzz": {
                "negativeControls": [
                    {"kernOff": [1], "kernOn": [1], "text": "L’O"},
                    {"kernOff": [2], "kernOn": [2], "text": "l’A"},
                    {"kernOff": [3], "kernOn": [3], "text": "’A"},
                ],
                "positiveKernOff": [600, 600, 600],
                "positiveKernOn": [559, 623, 600],
            },
            "nativeInput": {"boundaries": [1, 2], "sequence": ["L", "quoteright", "A"]},
        },
        "number_value_half_rounding": {
            "compiledAdjustments": [
                {"glyph": "A", "XPlacement": 3},
                {"glyph": "B", "XPlacement": -3},
                {"glyph": "C", "XPlacement": 1},
                {"glyph": "D", "XPlacement": -1},
            ],
            "exportedFeatureSource": "pos A <$positiveTwoHalf 0 0 0>;",
            "nativeInput": [
                {"glyph": "A", "name": "positiveTwoHalf", "value": 2.5},
                {"glyph": "B", "name": "negativeTwoHalf", "value": -2.5},
                {"glyph": "C", "name": "positiveHalf", "value": 0.5},
                {"glyph": "D", "name": "negativeHalf", "value": -0.5},
            ],
        },
    }
    for probe in payload["probes"]:
        probe["status"] = "captured"
        probe["observation"] = observations[probe["id"]]
    source_hash = "b" * 64
    payload["provenance"] = {
        "capturedAt": "2026-08-27T00:00:00Z",
        "harnessSha256": payload["captureHarness"]["sha256"],
        "host": {"application": "Glyphs", "build": "4004", "version": "4.0.1"},
        "pythonVersion": "3.14.6",
        "repositoryCommit": "a" * 40,
        "sourceBoundary": "detached_in_memory_probe",
        "workingDocument": {
            "changed": False,
            "disposable": True,
            "familyName": "Glyphs MCP V2 Disposable Unit Test",
            "saved": False,
            "sourceTreeSha256After": source_hash,
            "sourceTreeSha256Before": source_hash,
        },
    }
    fixture_path = root / "fixture.json"
    fixture_path.write_bytes(_json_bytes(payload))
    return fixture_path, payload


class Glyphs4NativeParityFixtureTests(unittest.TestCase):
    def test_capture_reuses_the_master_created_by_a_fresh_glyphs_font(self) -> None:
        default_master = object()

        class FakeFont:
            def __init__(self) -> None:
                self.masters = [default_master]

        class UnexpectedMaster:
            def __init__(self) -> None:
                raise AssertionError("the host default master must be reused")

        font, master = CAPTURE._fresh_probe_font_and_master(FakeFont, UnexpectedMaster)

        self.assertIs(master, default_master)
        self.assertEqual(font.masters, [default_master])

    def test_capture_adds_one_master_when_the_host_creates_none(self) -> None:
        created_master = object()

        class FakeFont:
            def __init__(self) -> None:
                self.masters = []

        class FakeMaster:
            def __new__(cls):
                return created_master

        font, master = CAPTURE._fresh_probe_font_and_master(FakeFont, FakeMaster)

        self.assertIs(master, created_master)
        self.assertEqual(font.masters, [created_master])

    def test_pending_fixture_is_valid_as_a_capture_plan_only(self) -> None:
        fixture = VALIDATOR.validate_fixture(FIXTURE, require_captured=False)
        self.assertEqual(fixture["captureStatus"], "capture_required")
        self.assertTrue(all(probe["observation"] is None for probe in fixture["probes"]))

    def test_release_qualification_refuses_pending_fixture(self) -> None:
        with self.assertRaises(VALIDATOR.FixtureValidationError) as caught:
            VALIDATOR.validate_fixture(FIXTURE, require_captured=True)
        self.assertEqual(caught.exception.code, "glyphs4_native_capture_required")

    def test_capture_plan_refuses_a_pre_4004_host_contract(self) -> None:
        payload = _pending_fixture()
        payload["requiredHost"]["minimumBuild"] = 4000
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / "fixture.json"
            fixture_path.write_bytes(_json_bytes(payload))
            with self.assertRaises(VALIDATOR.FixtureValidationError) as caught:
                VALIDATOR.validate_fixture(fixture_path, require_captured=False)
        self.assertEqual(caught.exception.code, "schema_invalid")

    def test_complete_synthetic_shape_validates_but_is_not_committed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path, _payload = _captured_fixture(Path(tmp))
            fixture = VALIDATOR.validate_fixture(fixture_path, require_captured=True)
        self.assertEqual(fixture["captureStatus"], "captured")

    def test_context_negative_control_must_remain_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path, payload = _captured_fixture(Path(tmp))
            context = next(
                probe for probe in payload["probes"] if probe["id"] == "contextual_boundary_semantics"
            )
            context["observation"]["harfbuzz"]["negativeControls"][0]["kernOn"] = [99]
            fixture_path.write_bytes(_json_bytes(payload))
            with self.assertRaises(VALIDATOR.FixtureValidationError) as caught:
                VALIDATOR.validate_fixture(fixture_path)
        self.assertEqual(caught.exception.code, "observation_invalid")

    def test_vertical_capture_requires_a_yadvance_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path, payload = _captured_fixture(Path(tmp))
            vertical = next(
                probe for probe in payload["probes"] if probe["id"] == "vertical_sign_yadvance"
            )
            vertical["observation"]["compiledGpos"]["yAdvance"] = 0
            fixture_path.write_bytes(_json_bytes(payload))
            with self.assertRaises(VALIDATOR.FixtureValidationError) as caught:
                VALIDATOR.validate_fixture(fixture_path)
        self.assertEqual(caught.exception.code, "observation_invalid")

    def test_number_capture_requires_both_signs_at_half_and_two_half(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path, payload = _captured_fixture(Path(tmp))
            numbers = next(
                probe for probe in payload["probes"] if probe["id"] == "number_value_half_rounding"
            )
            numbers["observation"]["nativeInput"].pop()
            fixture_path.write_bytes(_json_bytes(payload))
            with self.assertRaises(VALIDATOR.FixtureValidationError) as caught:
                VALIDATOR.validate_fixture(fixture_path)
        self.assertEqual(caught.exception.code, "observation_invalid")

    def test_artifact_hash_drift_is_a_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path, payload = _captured_fixture(Path(tmp))
            artifact = Path(tmp) / payload["artifactRoot"] / "native-observations.json"
            artifact.write_bytes(b"changed\n")
            with self.assertRaises(VALIDATOR.FixtureValidationError) as caught:
                VALIDATOR.validate_fixture(fixture_path)
        self.assertIn(caught.exception.code, {"artifact_drift", "artifact_inventory_mismatch"})

    def test_extra_artifact_symlink_is_a_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path, payload = _captured_fixture(Path(tmp))
            artifact_root = Path(tmp) / payload["artifactRoot"]
            (artifact_root / "unsafe-link").symlink_to("native-observations.json")
            with self.assertRaises(VALIDATOR.FixtureValidationError) as caught:
                VALIDATOR.validate_fixture(fixture_path)
        self.assertEqual(caught.exception.code, "artifact_invalid")

    def test_extra_artifact_special_object_is_a_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path, payload = _captured_fixture(Path(tmp))
            artifact_root = Path(tmp) / payload["artifactRoot"]
            os.mkfifo(artifact_root / "unsafe-fifo")
            with self.assertRaises(VALIDATOR.FixtureValidationError) as caught:
                VALIDATOR.validate_fixture(fixture_path)
        self.assertEqual(caught.exception.code, "artifact_invalid")

    def test_harness_hash_drift_is_a_blocker(self) -> None:
        payload = _pending_fixture()
        payload["captureHarness"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / "fixture.json"
            fixture_path.write_bytes(_json_bytes(payload))
            with self.assertRaises(VALIDATOR.FixtureValidationError) as caught:
                VALIDATOR.validate_fixture(fixture_path, require_captured=False)
        self.assertEqual(caught.exception.code, "harness_drift")

    def test_capture_harness_preserves_the_working_source_boundary(self) -> None:
        text = CAPTURE_PATH.read_text(encoding="utf-8")
        for required in (
            "detached in-memory font",
            "sourceTreeSha256Before",
            "sourceTreeSha256After",
            "working_changed",
            "probe_font",
            "font.export",
            "instance.generate",
        ):
            self.assertIn(required, text)
        for forbidden in (
            ".save(",
            "saveDocument_",
            "saveToURL_",
            "saveToURL_ofType_forSaveOperation_error_",
            ".show(",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn('int(float(build)) < 4004', text)
        self.assertIn('"minimumBuild": 4004', text)

    def test_complete_local_release_gate_requires_captured_evidence(self) -> None:
        release_script = (REPO / "scripts" / "run_local_release_tests.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            '"$python_bin" scripts/validate_glyphs4_native_parity.py',
            release_script,
        )
        self.assertNotIn(
            "validate_glyphs4_native_parity.py --schema-only",
            release_script,
        )

    def test_authentic_number_observations_drive_the_v2_rounding_contract(self) -> None:
        payload = _pending_fixture()
        if payload["captureStatus"] != "captured":
            self.assertIsNone(payload["provenance"])
            return
        from glyphs_mcp_v2.source_bundle import _decimal_expression

        numbers = next(
            probe for probe in payload["probes"] if probe["id"] == "number_value_half_rounding"
        )["observation"]
        by_glyph = {
            item["glyph"]: int(item["XPlacement"])
            for item in numbers["compiledAdjustments"]
        }
        for item in numbers["nativeInput"]:
            self.assertEqual(
                _decimal_expression("$" + item["name"], {item["name"]: item["value"]}),
                by_glyph[item["glyph"]],
            )


if __name__ == "__main__":
    unittest.main()
