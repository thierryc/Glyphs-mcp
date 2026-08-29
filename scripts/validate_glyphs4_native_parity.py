#!/usr/bin/env python3
"""Validate the committed Glyphs 4 native-export characterization fixture.

This gate intentionally has two modes:

* ``--schema-only`` validates a pending capture plan without qualifying it.
* the default release mode requires authentic, hashed Glyphs 4 observations.

A pending file is therefore useful in ordinary unit tests but can never make a
release candidate pass by omission, by a skipped host test, or by synthetic
expected values.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = (
    REPO_ROOT
    / "src"
    / "glyphs-mcp"
    / "tests"
    / "fixtures"
    / "glyphs4-native-export-parity.json"
)
FIXTURE_ID = "glyphs4-native-export-parity-v1"
SURFACE = "glyphs-mcp-v2"
CAPTURE_REQUIRED = "capture_required"
CAPTURED = "captured"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_PROBES = (
    "rtl_class_orientation",
    "vertical_sign_yadvance",
    "contextual_boundary_semantics",
    "number_value_half_rounding",
)


class FixtureValidationError(ValueError):
    """Raised when the fixture cannot qualify the v2 release."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


def _fail(code: str, message: str) -> None:
    raise FixtureValidationError(code, message)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("schema_invalid", f"{path} must be an object")
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        _fail("schema_invalid", f"{path} must be an array")
    return value


def _closed(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    path: str,
) -> None:
    keys = {str(key) for key in value}
    missing = sorted(required - keys)
    unknown = sorted(keys - required - optional)
    if missing:
        _fail("schema_invalid", f"{path} is missing {', '.join(missing)}")
    if unknown:
        _fail("schema_invalid", f"{path} has unknown fields {', '.join(unknown)}")


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("schema_invalid", f"{path} must be a non-empty string")
    return value


def _sha256(value: Any, path: str) -> str:
    text = _nonempty_string(value, path)
    if not SHA256_RE.fullmatch(text):
        _fail("schema_invalid", f"{path} must be a lowercase SHA-256")
    return text


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_utc(value: Any, path: str) -> str:
    text = _nonempty_string(value, path)
    if not text.endswith("Z"):
        _fail("schema_invalid", f"{path} must be an RFC 3339 UTC timestamp")
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        _fail("schema_invalid", f"{path} must be an RFC 3339 UTC timestamp: {exc}")
    return text


def _validate_required_host(value: Any) -> None:
    host = _mapping(value, "$.requiredHost")
    _closed(
        host,
        required={"application", "applicationMajor", "minimumBuild"},
        path="$.requiredHost",
    )
    if host["application"] != "Glyphs" or host["applicationMajor"] != 4:
        _fail("schema_invalid", "the fixture must characterize Glyphs 4")
    if not isinstance(host["minimumBuild"], int) or host["minimumBuild"] < 4004:
        _fail("schema_invalid", "$.requiredHost.minimumBuild must be 4004 or newer")


def _validate_harness(value: Any) -> tuple[Path, str]:
    harness = _mapping(value, "$.captureHarness")
    _closed(
        harness,
        required={"path", "sha256", "executionBoundary"},
        path="$.captureHarness",
    )
    relative = PurePosixPath(_nonempty_string(harness["path"], "$.captureHarness.path"))
    if relative.is_absolute() or ".." in relative.parts:
        _fail("schema_invalid", "$.captureHarness.path must stay inside the repository")
    if harness["executionBoundary"] != "glyphs4_disposable_detached_export":
        _fail("schema_invalid", "the capture harness boundary is not approved")
    expected_hash = _sha256(harness["sha256"], "$.captureHarness.sha256")
    path = REPO_ROOT.joinpath(*relative.parts)
    if path.is_symlink() or not path.is_file():
        _fail("harness_unavailable", f"capture harness is missing or unsafe: {path}")
    actual_hash = _file_sha256(path)
    if actual_hash != expected_hash:
        _fail(
            "harness_drift",
            f"capture harness hash is {actual_hash}, expected {expected_hash}",
        )
    return path, expected_hash


def _validate_probe_plan(value: Any, *, capture_status: str) -> dict[str, Mapping[str, Any]]:
    probes = _sequence(value, "$.probes")
    if len(probes) != len(REQUIRED_PROBES):
        _fail("schema_invalid", "$.probes must contain the four required characterizations")
    indexed: dict[str, Mapping[str, Any]] = {}
    for index, raw_probe in enumerate(probes):
        path = f"$.probes[{index}]"
        probe = _mapping(raw_probe, path)
        _closed(
            probe,
            required={"id", "objective", "requiredEvidence", "status", "observation"},
            path=path,
        )
        probe_id = _nonempty_string(probe["id"], f"{path}.id")
        if probe_id in indexed:
            _fail("schema_invalid", f"duplicate probe id {probe_id}")
        _nonempty_string(probe["objective"], f"{path}.objective")
        evidence = _sequence(probe["requiredEvidence"], f"{path}.requiredEvidence")
        if not evidence or any(not isinstance(item, str) or not item.strip() for item in evidence):
            _fail("schema_invalid", f"{path}.requiredEvidence must be non-empty strings")
        if probe["status"] != capture_status:
            _fail("schema_invalid", f"{path}.status must match $.captureStatus")
        if capture_status == CAPTURE_REQUIRED:
            if probe["observation"] is not None:
                _fail("synthetic_observation", f"{path}.observation must remain null before capture")
        else:
            observation = _mapping(probe["observation"], f"{path}.observation")
            if not observation:
                _fail("observation_missing", f"{path}.observation is empty")
        indexed[probe_id] = probe
    if tuple(indexed) != REQUIRED_PROBES:
        _fail(
            "schema_invalid",
            "$.probes must use the required deterministic order: "
            + ", ".join(REQUIRED_PROBES),
        )
    return indexed


def _numeric(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("observation_invalid", f"{path} must be numeric")
    return float(value)


def _validate_observations(probes: Mapping[str, Mapping[str, Any]]) -> None:
    rtl = _mapping(probes["rtl_class_orientation"]["observation"], "$.probes.rtl.observation")
    _closed(
        rtl,
        required={"nativeInput", "nativeStorage", "ufoGroups", "ufoKerning", "compiledGpos"},
        path="$.probes.rtl.observation",
    )
    if not _mapping(rtl["ufoGroups"], "$.probes.rtl.observation.ufoGroups"):
        _fail("observation_invalid", "RTL capture contains no exported UFO groups")
    if not _sequence(rtl["ufoKerning"], "$.probes.rtl.observation.ufoKerning"):
        _fail("observation_invalid", "RTL capture contains no exported UFO kerning")
    if not _mapping(rtl["compiledGpos"], "$.probes.rtl.observation.compiledGpos"):
        _fail("observation_invalid", "RTL capture contains no compiled GPOS evidence")

    vertical = _mapping(
        probes["vertical_sign_yadvance"]["observation"],
        "$.probes.vertical.observation",
    )
    _closed(
        vertical,
        required={"nativeInput", "compiledGpos", "harfbuzz"},
        path="$.probes.vertical.observation",
    )
    gpos = _mapping(vertical["compiledGpos"], "$.probes.vertical.observation.compiledGpos")
    _closed(
        gpos,
        required={"feature", "xAdvance", "yAdvance"},
        path="$.probes.vertical.observation.compiledGpos",
    )
    if gpos["feature"] != "vkrn":
        _fail("observation_invalid", "vertical native capture must identify vkrn")
    _numeric(gpos["xAdvance"], "$.probes.vertical.observation.compiledGpos.xAdvance")
    if _numeric(gpos["yAdvance"], "$.probes.vertical.observation.compiledGpos.yAdvance") == 0:
        _fail("observation_invalid", "vertical native capture has no YAdvance adjustment")
    hb_vertical = _mapping(vertical["harfbuzz"], "$.probes.vertical.observation.harfbuzz")
    _closed(hb_vertical, required={"vkrnOn", "vkrnOff"}, path="$.probes.vertical.observation.harfbuzz")
    if hb_vertical["vkrnOn"] == hb_vertical["vkrnOff"]:
        _fail("observation_invalid", "vertical shaping does not prove a vkrn effect")

    context = _mapping(
        probes["contextual_boundary_semantics"]["observation"],
        "$.probes.context.observation",
    )
    _closed(
        context,
        required={"nativeInput", "compiledGpos", "harfbuzz"},
        path="$.probes.context.observation",
    )
    hb_context = _mapping(context["harfbuzz"], "$.probes.context.observation.harfbuzz")
    _closed(
        hb_context,
        required={"positiveKernOn", "positiveKernOff", "negativeControls"},
        path="$.probes.context.observation.harfbuzz",
    )
    if hb_context["positiveKernOn"] == hb_context["positiveKernOff"]:
        _fail("observation_invalid", "context capture does not prove the positive sequence")
    controls = _sequence(
        hb_context["negativeControls"],
        "$.probes.context.observation.harfbuzz.negativeControls",
    )
    if len(controls) < 3:
        _fail("observation_invalid", "context capture requires at least three negative controls")
    for index, raw_control in enumerate(controls):
        control = _mapping(raw_control, f"$.probes.context.negativeControls[{index}]")
        _closed(
            control,
            required={"text", "kernOn", "kernOff"},
            path=f"$.probes.context.negativeControls[{index}]",
        )
        if control["kernOn"] != control["kernOff"]:
            _fail("observation_invalid", "a contextual negative control changed")

    numbers = _mapping(
        probes["number_value_half_rounding"]["observation"],
        "$.probes.numbers.observation",
    )
    _closed(
        numbers,
        required={"nativeInput", "exportedFeatureSource", "compiledAdjustments"},
        path="$.probes.numbers.observation",
    )
    inputs = _sequence(numbers["nativeInput"], "$.probes.numbers.observation.nativeInput")
    adjustments = _sequence(
        numbers["compiledAdjustments"],
        "$.probes.numbers.observation.compiledAdjustments",
    )
    required_ties = {-2.5, -0.5, 0.5, 2.5}
    captured_ties = {
        _numeric(item.get("value"), "$.probes.numbers.observation.nativeInput[].value")
        for item in inputs
        if isinstance(item, Mapping)
    }
    if not required_ties.issubset(captured_ties):
        _fail("observation_invalid", "Number Value capture omits positive or negative half ties")
    if len(adjustments) < len(required_ties):
        _fail("observation_invalid", "Number Value capture omits compiled adjustments")
    _nonempty_string(
        numbers["exportedFeatureSource"],
        "$.probes.numbers.observation.exportedFeatureSource",
    )


def _validate_provenance(
    value: Any,
    *,
    required_host: Mapping[str, Any],
    harness_hash: str,
) -> None:
    provenance = _mapping(value, "$.provenance")
    _closed(
        provenance,
        required={
            "capturedAt",
            "host",
            "pythonVersion",
            "repositoryCommit",
            "harnessSha256",
            "sourceBoundary",
            "workingDocument",
        },
        path="$.provenance",
    )
    _parse_utc(provenance["capturedAt"], "$.provenance.capturedAt")
    _nonempty_string(provenance["pythonVersion"], "$.provenance.pythonVersion")
    commit = _nonempty_string(provenance["repositoryCommit"], "$.provenance.repositoryCommit")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        _fail("provenance_invalid", "repositoryCommit must be a full Git object ID")
    if _sha256(provenance["harnessSha256"], "$.provenance.harnessSha256") != harness_hash:
        _fail("provenance_invalid", "captured harness hash disagrees with the committed harness")
    if provenance["sourceBoundary"] != "detached_in_memory_probe":
        _fail("provenance_invalid", "native capture did not use a detached in-memory probe")

    host = _mapping(provenance["host"], "$.provenance.host")
    _closed(host, required={"application", "version", "build"}, path="$.provenance.host")
    if host["application"] != "Glyphs":
        _fail("provenance_invalid", "capture host is not Glyphs")
    version = _nonempty_string(host["version"], "$.provenance.host.version")
    if version.split(".", 1)[0] != "4":
        _fail("provenance_invalid", "capture host is not Glyphs 4")
    try:
        build = int(float(str(host["build"])))
    except ValueError as exc:
        _fail("provenance_invalid", f"Glyphs build is not numeric: {exc}")
    if build < int(required_host["minimumBuild"]):
        _fail("provenance_invalid", "Glyphs build predates the required characterization host")

    working = _mapping(provenance["workingDocument"], "$.provenance.workingDocument")
    _closed(
        working,
        required={
            "familyName",
            "disposable",
            "saved",
            "changed",
            "sourceTreeSha256Before",
            "sourceTreeSha256After",
        },
        path="$.provenance.workingDocument",
    )
    if working["disposable"] is not True or working["saved"] is not False or working["changed"] is not False:
        _fail("provenance_invalid", "capture did not preserve the disposable working document")
    before = _sha256(
        working["sourceTreeSha256Before"],
        "$.provenance.workingDocument.sourceTreeSha256Before",
    )
    after = _sha256(
        working["sourceTreeSha256After"],
        "$.provenance.workingDocument.sourceTreeSha256After",
    )
    if before != after:
        _fail("provenance_invalid", "working source bytes changed during native capture")


def _validate_artifacts(value: Any, *, fixture_path: Path, artifact_root: Any) -> None:
    root_text = _nonempty_string(artifact_root, "$.artifactRoot")
    root_relative = PurePosixPath(root_text)
    if root_relative.is_absolute() or ".." in root_relative.parts:
        _fail("schema_invalid", "$.artifactRoot must stay below the fixture directory")
    root = fixture_path.parent.joinpath(*root_relative.parts)
    if root.is_symlink() or not root.is_dir():
        _fail("artifact_unavailable", f"artifact root is missing or unsafe: {root}")

    entries = _sequence(value, "$.artifacts")
    if not entries:
        _fail("artifact_unavailable", "captured fixture lists no native artifacts")
    declared: set[str] = set()
    for index, raw_entry in enumerate(entries):
        path = f"$.artifacts[{index}]"
        entry = _mapping(raw_entry, path)
        _closed(entry, required={"relativePath", "byteSize", "sha256"}, path=path)
        relative_text = _nonempty_string(entry["relativePath"], f"{path}.relativePath")
        relative = PurePosixPath(relative_text)
        if relative.is_absolute() or ".." in relative.parts or relative_text in declared:
            _fail("artifact_invalid", f"unsafe or duplicate artifact path {relative_text}")
        declared.add(relative_text)
        artifact = root.joinpath(*relative.parts)
        try:
            mode = artifact.lstat().st_mode
        except FileNotFoundError:
            _fail("artifact_unavailable", f"missing native artifact {relative_text}")
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            _fail("artifact_invalid", f"native artifact is not a regular file: {relative_text}")
        if not isinstance(entry["byteSize"], int) or entry["byteSize"] < 0:
            _fail("schema_invalid", f"{path}.byteSize must be a non-negative integer")
        if artifact.stat().st_size != entry["byteSize"]:
            _fail("artifact_drift", f"native artifact size changed: {relative_text}")
        expected_hash = _sha256(entry["sha256"], f"{path}.sha256")
        if _file_sha256(artifact) != expected_hash:
            _fail("artifact_drift", f"native artifact hash changed: {relative_text}")

    observed: set[str] = set()
    for child in root.rglob("*"):
        relative_text = child.relative_to(root).as_posix()
        mode = child.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            _fail(
                "artifact_invalid",
                f"native artifact inventory contains a link or special object: {relative_text}",
            )
        if stat.S_ISREG(mode):
            observed.add(relative_text)
    if observed != declared:
        missing = sorted(declared - observed)
        extra = sorted(observed - declared)
        _fail(
            "artifact_inventory_mismatch",
            f"native artifact inventory differs; missing={missing}, extra={extra}",
        )


def validate_fixture(
    fixture_path: Path = DEFAULT_FIXTURE,
    *,
    require_captured: bool = True,
) -> Mapping[str, Any]:
    fixture_path = Path(fixture_path)
    try:
        raw = fixture_path.read_bytes()
    except OSError as exc:
        _fail("fixture_unavailable", f"cannot read native parity fixture: {exc}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail("schema_invalid", f"fixture must be deterministic UTF-8 JSON: {exc}")
    if raw != (json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8"):
        _fail("fixture_not_deterministic", "fixture JSON must use sorted keys, two-space indentation, and one final newline")

    root = _mapping(payload, "$")
    _closed(
        root,
        required={
            "schemaVersion",
            "fixtureId",
            "surface",
            "captureStatus",
            "requiredHost",
            "captureHarness",
            "probes",
            "provenance",
            "artifactRoot",
            "artifacts",
            "blocker",
        },
        path="$",
    )
    if root["schemaVersion"] != 1 or root["fixtureId"] != FIXTURE_ID or root["surface"] != SURFACE:
        _fail("schema_invalid", "fixture identity does not match the v2 native parity contract")
    capture_status = root["captureStatus"]
    if capture_status not in {CAPTURE_REQUIRED, CAPTURED}:
        _fail("schema_invalid", "$.captureStatus must be capture_required or captured")
    _validate_required_host(root["requiredHost"])
    _harness_path, harness_hash = _validate_harness(root["captureHarness"])
    probes = _validate_probe_plan(root["probes"], capture_status=capture_status)

    if capture_status == CAPTURE_REQUIRED:
        if root["provenance"] is not None or root["artifacts"] != [] or root["artifactRoot"] is not None:
            _fail("synthetic_observation", "pending capture must not contain provenance or artifacts")
        blocker = _mapping(root["blocker"], "$.blocker")
        _closed(blocker, required={"code", "message", "requiredAction"}, path="$.blocker")
        if blocker["code"] != "glyphs4_native_capture_required":
            _fail("schema_invalid", "pending fixture has the wrong blocker code")
        _nonempty_string(blocker["message"], "$.blocker.message")
        _nonempty_string(blocker["requiredAction"], "$.blocker.requiredAction")
        if require_captured:
            _fail(
                "glyphs4_native_capture_required",
                "Glyphs 4 native-export parity evidence is pending; run the committed capture harness on an approved disposable Glyphs 4 document and commit its hashed artifacts",
            )
        return root

    if root["blocker"] is not None:
        _fail("schema_invalid", "captured fixture cannot retain a blocker")
    required_host = _mapping(root["requiredHost"], "$.requiredHost")
    _validate_provenance(
        root["provenance"],
        required_host=required_host,
        harness_hash=harness_hash,
    )
    _validate_observations(probes)
    _validate_artifacts(
        root["artifacts"],
        fixture_path=fixture_path,
        artifact_root=root["artifactRoot"],
    )
    return root


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="validate the capture plan but allow capture_required status",
    )
    arguments = parser.parse_args(argv)
    try:
        fixture = validate_fixture(
            arguments.fixture,
            require_captured=not arguments.schema_only,
        )
    except FixtureValidationError as exc:
        print(f"Glyphs 4 native parity gate failed [{exc.code}]: {exc}", file=sys.stderr)
        return 1
    print(
        "Glyphs 4 native parity fixture is {}: {}".format(
            fixture["captureStatus"],
            arguments.fixture,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
