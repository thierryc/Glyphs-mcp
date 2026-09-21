"""Closed OpenType compilation and staged export contracts."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest


ROOT = Path(__file__).resolve().parents[3]
for part in ("protocol", "bridge", "sidecar"):
    sys.path.insert(0, str(ROOT / "src" / part))

from glyphs_mcp_protocol import ProtocolError  # noqa: E402
from glyphs_mcp_protocol.compile_export import (  # noqa: E402
    JOB_CAPABILITIES,
    recognized_job_capabilities,
    validate_compile_options,
    validate_export_options,
    validate_worker_result,
)
from glyphs_mcp_bridge.core import BridgeError  # noqa: E402
from glyphs_mcp_bridge.glyphs_adapter import GlyphsAdapter  # noqa: E402
from glyphs_mcp_sidecar.jobs import JobStore  # noqa: E402
from glyphs_mcp_sidecar import feature_compile_job  # noqa: E402
from glyphs_mcp_sidecar import font_export_job  # noqa: E402
from glyphs_mcp_sidecar.service import ServiceError, SidecarService  # noqa: E402
from glyphs_mcp_sidecar.worker import WorkerError  # noqa: E402


HASH = "sha256:" + "a" * 64


class _Collection(list):
    def __getitem__(self, key):
        if isinstance(key, str):
            for item in self:
                if key in (str(getattr(item, "id", "")), str(getattr(item, "name", ""))):
                    return item
            raise KeyError(key)
        return super().__getitem__(key)


class _Document:
    def __init__(self):
        self.changeCount = 4
        self.isDocumentEdited = False


def _read_fixture():
    prefix = NS(
        id="prefix-1", name="Languagesystems", code="languagesystem DFLT dflt;",
        automatic=False, disabled=False, canBeAutomated=False, notes="prefix note",
        labels=[], errors=[], errorType=0, errorTooltip=None, filePath=None,
    )
    feature_a = NS(
        id="feature-1", name="liga", code="sub f i by fi;", automatic=True,
        disabled=False, canBeAutomated=True, notes="", labels=["Ligatures"],
        errors=[], errorType=0, errorTooltip=None, filePath=None,
    )
    feature_b = NS(
        id="feature-2", name="kern", code="pos A V -80;", automatic=False,
        disabled=True, canBeAutomated=False, notes="", labels=[], errors=["bad pair"],
        errorType=1, errorTooltip="bad pair", filePath="features.fea",
    )
    static = NS(
        id="instance-1", name="Regular", type=0, exports=True, outlineFormat=0,
        axes=[400.0], active=True,
    )
    variable = NS(
        id="instance-2", name="Variable", type=1, exports=True, outlineFormat=1,
        axes=[100.0, 900.0], active=True,
    )
    document = _Document()
    font = NS(
        filepath="/tmp/Features.glyphs", familyName="Features", parent=document,
        featurePrefixes=_Collection([prefix]), classes=_Collection(),
        features=_Collection([feature_a, feature_b]),
        instances=_Collection([static, variable]), axes=_Collection(), glyphs=_Collection(),
    )
    adapter = GlyphsAdapter(NS(fonts=[font], font=font))
    return adapter, font, document, prefix, feature_a, feature_b, static, variable


def test_compile_options_are_closed_and_saved_is_the_safe_default():
    assert validate_compile_options({}) == {"mode": "saved"}
    assert validate_compile_options({"mode": "live"}) == {"mode": "live"}
    with pytest.raises(ProtocolError, match="unexpected fields"):
        validate_compile_options({"mode": "saved", "selector": "compileTempFontError:"})
    with pytest.raises(ProtocolError, match="saved or live"):
        validate_compile_options({"mode": "temporary"})


def test_export_options_normalize_typed_defaults_and_reject_open_ended_input():
    value = validate_export_options({"instanceId": "instance-1", "format": "otf"})
    assert value == {
        "instanceId": "instance-1",
        "format": "otf",
        "containers": ["plain"],
        "generation": {
            "autoHint": True,
            "removeOverlap": None,
            "useSubroutines": True,
            "useProductionNames": True,
            "decomposeSmartComponents": True,
        },
        "verification": {"shapingCases": []},
    }
    with pytest.raises(ProtocolError, match="unexpected fields"):
        validate_export_options({"instanceId": "instance-1", "format": "otf", "python": "font.export()"})
    with pytest.raises(ProtocolError, match="unique"):
        validate_export_options({"instanceId": "instance-1", "format": "otf", "containers": ["plain", "plain"]})
    with pytest.raises(ProtocolError, match="TTF"):
        validate_export_options({
            "instanceId": "instance-1", "format": "ttf",
            "generation": {"useSubroutines": True},
        })


def test_shaping_cases_are_bounded_explicit_expectations():
    options = validate_export_options({
        "instanceId": "variable-1",
        "format": "otf",
        "verification": {"shapingCases": [{
            "text": "ffi", "feature": "liga", "expect": "different",
            "controlText": "abc", "direction": "ltr", "script": "latn",
            "language": "dflt", "variations": {"wght": 700},
        }]},
    })
    assert options["verification"]["shapingCases"][0]["feature"] == "liga"
    with pytest.raises(ProtocolError, match="four printable ASCII"):
        validate_export_options({
            "instanceId": "instance-1", "format": "otf",
            "verification": {"shapingCases": [{
                "text": "ffi", "feature": "ligature", "expect": "different",
            }]},
        })
    with pytest.raises(ProtocolError, match="0-32"):
        validate_export_options({
            "instanceId": "instance-1", "format": "otf",
            "verification": {"shapingCases": [
                {"text": "ffi", "feature": "liga", "expect": "different"}
                for _ in range(33)
            ]},
        })


def test_job_capabilities_are_closed_and_sorted():
    assert JOB_CAPABILITIES
    assert recognized_job_capabilities([
        "unknown", "font.verify.tables.v1", "feature.compile.saved.v1",
        "font.verify.tables.v1",
    ]) == ["feature.compile.saved.v1", "font.verify.tables.v1"]


def test_worker_result_union_keeps_mutations_diagnostics_and_artifacts_distinct():
    diagnostic = validate_worker_result({
        "version": 1, "resultKind": "diagnostic", "jobId": "job_1",
        "documentId": "doc", "sourcePath": "/tmp/A.glyphs",
        "sourceHash": HASH, "generation": 3, "summary": "Compilation failed",
        "report": {"success": False, "mode": "saved", "errors": [{"message": "bad lookup"}]},
    })
    assert diagnostic["resultKind"] == "diagnostic" and diagnostic["report"]["success"] is False

    artifact = validate_worker_result({
        "version": 1, "resultKind": "artifact", "jobId": "job_2",
        "documentId": "doc", "sourcePath": "/tmp/A.glyphs",
        "sourceHash": HASH, "generation": 3, "summary": "Exported Regular",
        "manifest": {"files": [{
            "path": "Regular.otf", "size": 4,
            "sha256": "sha256:" + hashlib.sha256(b"font").hexdigest(),
            "format": "otf", "container": "plain", "mediaType": "font/otf",
        }], "totalBytes": 4},
        "report": {"success": True, "verification": {"tables": True}},
    })
    assert artifact["resultKind"] == "artifact"
    with pytest.raises(ProtocolError, match="relative"):
        validate_worker_result({
            **artifact,
            "manifest": {**artifact["manifest"], "files": [
                {**artifact["manifest"]["files"][0], "path": "/tmp/Regular.otf"}
            ]},
        })


def test_service_filters_job_capabilities_and_rejects_unadvertised_modes(tmp_path):
    source = tmp_path / "A.glyphs"
    source.write_text("font", encoding="utf-8")
    document = {"id": "doc", "path": str(source), "dirty": False, "generation": 1}
    bridge = NS(
        documents=lambda: [document],
        status=lambda: {
            "jobCapabilities": ["feature.compile.live.v1", "unknown"],
            "readCapabilities": [], "writeCapabilities": [], "nativeActions": [],
        },
    )
    worker = NS(status=lambda: {
        "available": True,
        "jobCapabilities": ["feature.compile.saved.v1", "font.export.static.v1", "font.verify.tables.v1", "unknown"],
    })
    service = SidecarService(bridge, jobs=JobStore(tmp_path / "jobs"), worker=worker)
    status = service.get_status()
    assert status["jobCapabilities"] == [
        "feature.compile.live.v1", "feature.compile.saved.v1", "font.export.static.v1",
        "font.verify.tables.v1",
    ]
    assert "feature_compile" in status["jobKinds"] and "font_export" in status["jobKinds"]

    bridge.status = lambda: {"jobCapabilities": [], "readCapabilities": [], "writeCapabilities": []}
    worker.status = lambda: {"available": True, "jobCapabilities": []}
    with pytest.raises(ServiceError) as error:
        service.start_job("doc", kind="feature_compile", options={"mode": "saved"})
    assert error.value.code == "unsupported_job"


def test_feature_block_pages_use_exact_persistent_ids_and_stale_checked_cursors():
    adapter, _font, document, _prefix, _first, _second, _static, _variable = _read_fixture()
    document_id = adapter.list_documents()[0]["id"]
    first = adapter.read_entities(
        document_id,
        [{"kind": "feature_blocks", "blockType": "feature", "limit": 1}],
        ["items"],
    )[0]["values"]
    assert first["items"] == [{
        "id": "feature-1", "name": "liga", "automatic": True,
        "disabled": False, "canBeAutomated": True,
        "codeLength": len("sub f i by fi;"), "errorCount": 0,
    }]
    assert first["complete"] is False and first["nextCursor"].startswith("f1.")
    second = adapter.read_entities(
        document_id,
        [{"kind": "feature_blocks", "blockType": "feature", "limit": 1,
          "cursor": first["nextCursor"]}],
        ["items"],
    )[0]["values"]
    assert second["items"][0]["id"] == "feature-2" and second["complete"] is True
    document.changeCount += 1
    with pytest.raises(BridgeError) as error:
        adapter.read_entities(
            document_id,
            [{"kind": "feature_blocks", "blockType": "feature", "limit": 1,
              "cursor": first["nextCursor"]}],
            ["items"],
        )
    assert error.value.code == "stale_feature_cursor"


def test_exact_feature_block_reads_only_requested_fields():
    adapter, *_rest = _read_fixture()
    document_id = adapter.list_documents()[0]["id"]
    result = adapter.read_entities(
        document_id,
        [{"kind": "feature_block", "blockType": "feature", "id": "feature-1"}],
        ["id", "name", "code", "automatic", "labels", "errors"],
    )[0]
    assert result["entity"]["id"] == "feature-1"
    assert result["values"] == {
        "id": "feature-1", "name": "liga", "code": "sub f i by fi;",
        "automatic": True, "labels": ["Ligatures"], "errors": [],
    }
    with pytest.raises(BridgeError) as error:
        adapter.read_entities(
            document_id,
            [{"kind": "feature_block", "blockType": "feature", "id": "liga"}],
            ["code"],
        )
    assert error.value.code == "target_not_found"


def test_instance_pages_and_exact_reads_distinguish_static_and_variable():
    adapter, *_rest = _read_fixture()
    document_id = adapter.list_documents()[0]["id"]
    page = adapter.read_entities(
        document_id, [{"kind": "instances", "limit": 100}], ["items"]
    )[0]["values"]
    assert page["items"] == [
        {"id": "instance-1", "name": "Regular", "type": "static", "exports": True, "outlineFormat": "otf"},
        {"id": "instance-2", "name": "Variable", "type": "variable", "exports": True, "outlineFormat": "ttf"},
    ]
    exact = adapter.read_entities(
        document_id, [{"kind": "instance", "id": "instance-2"}],
        ["id", "name", "type", "exports", "outlineFormat", "axisValues"],
    )[0]["values"]
    assert exact == {
        "id": "instance-2", "name": "Variable", "type": "variable",
        "exports": True, "outlineFormat": "ttf", "axisValues": [100.0, 900.0],
    }


def _wait(service, job_id, status):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = service.get_job(job_id)
        if job["status"] == status:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not reach {status}")


class _FeatureBlock:
    def __init__(self, identity="feature-1", name="liga", code="sub f i by fi;"):
        self.id = identity
        self.name = name
        self.code = code
        self.automatic = False
        self.disabled = False
        self.errors = []

    def propertyListValueFormat_(self, _format):
        return {"id": self.id, "name": self.name, "code": self.code,
                "automatic": self.automatic, "disabled": self.disabled}


class _CompileFont:
    def __init__(self, result):
        self.featurePrefixes = _Collection()
        self.classes = _Collection()
        self.features = _Collection([_FeatureBlock()])
        self._result = result

    def compileFeatures(self):
        return self._result


def test_saved_compile_worker_reports_compiler_failure_as_diagnostic_not_job_failure():
    font = _CompileFont((False, NS(localizedDescription="Unknown glyph fi", domain="com.glyphs", code=7)))
    report = feature_compile_job.prepare(font, {"kind": "feature_compile", "options": {"mode": "saved"}})
    assert report["success"] is False and report["mode"] == "saved"
    assert report["beforeHash"] == report["afterHash"]
    assert report["errors"][0]["message"] == "Unknown glyph fi"


def test_saved_compile_service_finishes_terminal_without_apply_accept_or_discard(tmp_path):
    source = tmp_path / "Compile.glyphs"
    source.write_text("font source", encoding="utf-8")
    document = {"id": "doc", "path": str(source), "dirty": False, "generation": 2}
    bridge = NS(
        documents=lambda: [dict(document)],
        status=lambda: {"jobCapabilities": [], "readCapabilities": [], "writeCapabilities": []},
    )

    class Worker:
        @staticmethod
        def status():
            return {"available": True, "jobCapabilities": ["feature.compile.saved.v1"]}

        @staticmethod
        def prepare(job_root, observed, request, _snapshot, source_hash, _cancel):
            assert request == {"kind": "feature_compile", "glyphs": [], "options": {"mode": "saved"}}
            return {
                "version": 1, "resultKind": "diagnostic", "jobId": job_root.name,
                "documentId": observed["id"], "sourcePath": observed["path"],
                "sourceHash": source_hash, "generation": observed["generation"],
                "summary": "OpenType compilation failed",
                "report": {
                    "claim": "Saved-source OpenType compilation diagnostics",
                    "success": False, "mode": "saved", "ephemeral": False,
                    "errors": [{"message": "Unknown glyph fi"}], "warnings": [],
                },
            }

    service = SidecarService(bridge, jobs=JobStore(tmp_path / "jobs"), worker=Worker())
    job = service.start_job("doc", kind="feature_compile", options={})
    completed = _wait(service, job["id"], "completed")
    assert completed["resultKind"] == "diagnostic"
    assert completed["report"]["success"] is False
    assert completed["changeCount"] == 0
    for operation in (service.apply_job, service.accept_job, service.discard_job):
        with pytest.raises(ServiceError) as error:
            operation(job["id"])
        assert error.value.code in {"job_not_applicable", "job_not_acceptable", "job_not_discardable"}


def test_live_compile_runs_on_start_without_requiring_the_external_worker(tmp_path):
    source = tmp_path / "Live.glyphs"
    source.write_text("live font", encoding="utf-8")
    document = {"id": "doc", "path": str(source), "dirty": False, "generation": 5}
    calls = []

    class Bridge:
        def documents(self):
            return [dict(document)]

        def status(self):
            return {"jobCapabilities": ["feature.compile.live.v1"],
                    "readCapabilities": [], "writeCapabilities": []}

        def compile_features(self, request):
            calls.append(request)
            return {
                "claim": "Live-editor OpenType compilation diagnostics",
                "success": True, "mode": "live", "ephemeral": True,
                "beforeHash": HASH, "afterHash": HASH,
                "errors": [], "warnings": [], "blockCount": 1,
            }

    class UnavailableWorker:
        @staticmethod
        def status():
            return {"available": False, "jobCapabilities": []}

        @staticmethod
        def prepare(*_args):
            raise AssertionError("live compile must not invoke the external worker")

    service = SidecarService(
        Bridge(), jobs=JobStore(tmp_path / "jobs"), worker=UnavailableWorker()
    )
    job = service.start_job("doc", kind="feature_compile", options={"mode": "live"})
    completed = _wait(service, job["id"], "completed")
    assert completed["report"]["ephemeral"] is True
    assert calls[0]["jobId"] == job["id"]
    assert calls[0]["sourceHash"].startswith("sha256:")


def test_bridge_status_exposes_live_compile_only_when_qualified(monkeypatch):
    from glyphs_mcp_bridge.core import BridgeCore

    core = BridgeCore(NS(), lambda callback: callback())
    monkeypatch.setattr("glyphs_mcp_bridge.core.feature_compile.available", lambda: False)
    assert "feature.compile.live.v1" not in core.status()["jobCapabilities"]
    monkeypatch.setattr("glyphs_mcp_bridge.core.feature_compile.available", lambda: True)
    assert core.status()["jobCapabilities"] == ["feature.compile.live.v1"]


def _artifact_worker():
    class Worker:
        @staticmethod
        def status():
            return {
                "available": True,
                "jobCapabilities": [
                    "font.export.static.v1", "font.verify.tables.v1"
                ],
            }

        @staticmethod
        def prepare(job_root, document, request, _snapshot, source_hash, _cancel):
            assert request["kind"] == "font_export"
            staging = job_root / "artifacts"
            staging.mkdir()
            payload = b"verified font bytes"
            output = staging / "Regular.ttf"
            output.write_bytes(payload)
            digest = "sha256:" + hashlib.sha256(payload).hexdigest()
            return {
                "version": 1, "resultKind": "artifact", "jobId": job_root.name,
                "documentId": document["id"], "sourcePath": document["path"],
                "sourceHash": source_hash, "generation": document["generation"],
                "summary": "Exported Regular",
                "manifest": {"files": [{
                    "path": "Regular.ttf", "size": len(payload), "sha256": digest,
                    "format": "ttf", "container": "plain", "mediaType": "font/ttf",
                }], "totalBytes": len(payload)},
                "report": {
                    "claim": "Staged and structurally verified font export",
                    "success": True, "instanceId": "instance-1", "instanceType": "static",
                    "verification": {"tables": True, "shapingCases": []}, "warnings": [],
                },
            }

    return Worker()


def _artifact_service(tmp_path):
    source = tmp_path / "Export.glyphs"
    source.write_text("font source", encoding="utf-8")
    document = {"id": "doc", "path": str(source), "dirty": False, "generation": 7}
    bridge = NS(
        documents=lambda: [dict(document)],
        status=lambda: {"jobCapabilities": [], "readCapabilities": [], "writeCapabilities": []},
    )
    service = SidecarService(
        bridge, jobs=JobStore(tmp_path / "jobs"), worker=_artifact_worker()
    )
    return service, bridge, document, source


def test_artifact_job_stages_without_apply_and_accepts_to_a_new_directory(tmp_path):
    service, _bridge, _document, _source = _artifact_service(tmp_path)
    job = service.start_job(
        "doc", kind="font_export",
        options={"instanceId": "instance-1", "format": "ttf"},
    )
    ready = _wait(service, job["id"], "ready")
    assert ready["resultKind"] == "artifact"
    assert ready["manifest"]["files"][0]["path"] == "Regular.ttf"
    with pytest.raises(ServiceError) as error:
        service.apply_job(job["id"])
    assert error.value.code == "job_not_applicable"

    destination = tmp_path / "published"
    accepted = service.accept_job(job["id"], destination=str(destination))
    assert accepted["status"] == "accepted"
    assert destination.joinpath("Regular.ttf").read_bytes() == b"verified font bytes"
    assert accepted["receipt"]["verification"] == "staged_artifacts_and_source_hash"
    assert sorted(item.name for item in service.jobs.path(job["id"]).iterdir()) == [
        "receipt.json", "state.json"
    ]


def test_artifact_acceptance_rejects_stale_source_and_existing_destination(tmp_path):
    service, _bridge, _document, source = _artifact_service(tmp_path)
    job = service.start_job(
        "doc", kind="font_export",
        options={"instanceId": "instance-1", "format": "ttf"},
    )
    _wait(service, job["id"], "ready")
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ServiceError) as error:
        service.accept_job(job["id"], destination=str(existing))
    assert error.value.code == "destination_exists"
    source.write_text("changed source", encoding="utf-8")
    with pytest.raises(ServiceError) as error:
        service.accept_job(job["id"], destination=str(tmp_path / "new"))
    assert error.value.code == "stale_source"
    assert service.jobs.get(job["id"])["status"] == "ready"


def test_artifact_discard_deletes_private_staging(tmp_path):
    service, *_rest = _artifact_service(tmp_path)
    job = service.start_job(
        "doc", kind="font_export",
        options={"instanceId": "instance-1", "format": "ttf"},
    )
    _wait(service, job["id"], "ready")
    assert service.jobs.path(job["id"]).joinpath("artifacts", "Regular.ttf").is_file()
    assert service.discard_job(job["id"])["status"] == "discarded"
    assert [item.name for item in service.jobs.path(job["id"]).iterdir()] == ["state.json"]


def test_artifact_receipt_reconciles_an_interrupted_acceptance_after_restart(tmp_path):
    service, bridge, _document, _source = _artifact_service(tmp_path)
    job = service.start_job(
        "doc", kind="font_export",
        options={"instanceId": "instance-1", "format": "ttf"},
    )
    _wait(service, job["id"], "ready")
    destination = tmp_path / "published-restart"
    service.accept_job(job["id"], destination=str(destination))
    service.jobs.update(job["id"], status="accepting")

    restarted = SidecarService(
        bridge, jobs=JobStore(service.jobs.root), worker=_artifact_worker()
    )
    assert restarted.get_job(job["id"])["status"] == "accepted"


def test_artifact_destination_reconstructs_a_missing_receipt_after_rename(tmp_path):
    service, bridge, _document, _source = _artifact_service(tmp_path)
    job = service.start_job(
        "doc", kind="font_export",
        options={"instanceId": "instance-1", "format": "ttf"},
    )
    _wait(service, job["id"], "ready")
    destination = tmp_path / "published-recovered"
    service.accept_job(job["id"], destination=str(destination))
    receipt_path = service.jobs.path(job["id"]) / "receipt.json"
    receipt_path.unlink()
    service.jobs.update(
        job["id"], status="accepting", receipt=None,
        publishRequest={"destination": str(destination)},
    )
    # Recreate the durable manifest/staging state that exists when a process
    # exits immediately after the atomic directory rename.
    manifest = {
        "files": [{
            "path": "Regular.ttf", "size": len(b"verified font bytes"),
            "sha256": "sha256:" + hashlib.sha256(b"verified font bytes").hexdigest(),
            "format": "ttf", "container": "plain", "mediaType": "font/ttf",
        }],
        "totalBytes": len(b"verified font bytes"),
    }
    service.jobs.write_json(job["id"], "manifest.json", manifest)

    restarted = SidecarService(
        bridge, jobs=JobStore(service.jobs.root), worker=_artifact_worker()
    )
    accepted = restarted.get_job(job["id"])
    assert accepted["status"] == "accepted"
    assert accepted["receipt"]["recovered"] is True


def _build_minimal_ttf(output):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "A"])
    builder.setupCharacterMap({65: "A"})
    pen = TTGlyphPen(None)
    notdef = pen.glyph()
    pen = TTGlyphPen(None)
    pen.moveTo((100, 0)); pen.lineTo((500, 700)); pen.lineTo((900, 0)); pen.closePath()
    builder.setupGlyf({".notdef": notdef, "A": pen.glyph()})
    builder.setupHorizontalMetrics({".notdef": (500, 0), "A": (1000, 50)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Minimal", "styleName": "Regular",
                            "uniqueFontIdentifier": "Minimal Regular",
                            "fullName": "Minimal Regular", "psName": "Minimal-Regular"})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                     usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    builder.save(output)


def _build_feature_ttf(output):
    from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont

    order = [".notdef", "A", "A.alt", "B"]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap({65: "A", 66: "B"})
    glyphs = {}
    for name in order:
        pen = TTGlyphPen(None)
        if name != ".notdef":
            inset = {"A": 100, "A.alt": 200, "B": 300}[name]
            pen.moveTo((inset, 0)); pen.lineTo((500, 700)); pen.lineTo((1000 - inset, 0)); pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (1000, 0) for name in order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Feature", "styleName": "Regular",
                            "uniqueFontIdentifier": "Feature Regular",
                            "fullName": "Feature Regular", "psName": "Feature-Regular"})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                     usWinAscent=800, usWinDescent=200)
    builder.setupPost(); builder.setupMaxp(); builder.save(output)
    font = TTFont(output)
    addOpenTypeFeaturesFromString(font, "feature salt { sub A by A.alt; } salt;")
    font.save(output); font.close()


def test_table_verifier_accepts_a_minimal_true_type_font(tmp_path):
    output = tmp_path / "Minimal.ttf"
    _build_minimal_ttf(output)
    evidence = font_export_job.verify_font(output, requested_format="ttf", container="plain", variable=False)
    assert evidence["format"] == "ttf"
    assert {"head", "cmap", "glyf", "loca"}.issubset(evidence["tables"])


@pytest.mark.parametrize("flavor", ["woff", "woff2"])
def test_web_containers_reopen_and_verify_as_the_requested_flavor(tmp_path, flavor):
    from fontTools.ttLib import TTFont

    source = tmp_path / "Minimal.ttf"
    output = tmp_path / ("Minimal." + flavor)
    _build_minimal_ttf(source)
    font = TTFont(source)
    font.flavor = flavor
    font.save(output)
    font.close()
    evidence = font_export_job.verify_font(
        output, requested_format="ttf", container=flavor, variable=False
    )
    assert evidence["container"] == flavor


def test_harfbuzz_cases_compare_feature_on_off_and_unchanged_controls(tmp_path):
    output = tmp_path / "Minimal.ttf"
    _build_minimal_ttf(output)
    same = font_export_job._shape(output, {
        "text": "A", "feature": "liga", "expect": "same", "value": 1,
        "controlText": "A",
    })
    assert same["passed"] and same["controlPassed"]
    with pytest.raises(WorkerError, match="expected different"):
        font_export_job._shape(output, {
            "text": "A", "feature": "liga", "expect": "different", "value": 1,
        })

    featured = tmp_path / "Feature.ttf"
    _build_feature_ttf(featured)
    changed = font_export_job._shape(featured, {
        "text": "A", "feature": "salt", "expect": "different", "value": 1,
        "controlText": "B",
    })
    assert changed["off"] != changed["on"] and changed["controlPassed"]
    from fontTools.ttLib import TTFont
    for flavor in ("woff", "woff2"):
        web = tmp_path / ("Feature." + flavor)
        font = TTFont(featured); font.flavor = flavor; font.save(web); font.close()
        result = font_export_job._shape(web, {
            "text": "A", "feature": "salt", "expect": "different", "value": 1,
            "controlText": "B",
        })
        assert result["off"] != result["on"] and result["controlPassed"]


def test_native_instance_generation_uses_only_normalized_typed_options(tmp_path):
    calls = []

    class Instance:
        id = "instance-1"
        name = "Regular"
        type = 0
        exports = True

        def generate(self, **options):
            calls.append(options)
            _build_minimal_ttf(Path(options["fontPath"]) / "Regular.ttf")
            return None

    options = validate_export_options({
        "instanceId": "instance-1", "format": "ttf", "containers": ["plain"],
        "verification": {"shapingCases": [{
            "text": "A", "feature": "liga", "expect": "same"
        }]},
    })
    manifest, report = font_export_job.prepare(
        NS(instances=[Instance()]), {"kind": "font_export", "options": options}, tmp_path
    )
    assert manifest["files"][0]["path"] == "Regular.ttf"
    assert report["verification"]["tables"] is True
    assert calls[0]["removeOverlap"] is True
    assert calls[0]["useSubroutines"] is False
    assert set(calls[0]) == {
        "format", "fontPath", "autoHint", "removeOverlap", "useSubroutines",
        "useProductionNames", "containers", "decomposeSmartStuff",
    }


def test_variable_export_rejects_overlap_removal_before_native_generation(tmp_path):
    instance = NS(id="variable-1", name="Variable", type=1, exports=True,
                  generate=lambda **_options: (_ for _ in ()).throw(AssertionError("must not generate")))
    options = validate_export_options({
        "instanceId": "variable-1", "format": "ttf",
        "generation": {"removeOverlap": True},
    })
    with pytest.raises(WorkerError, match="variable"):
        font_export_job.prepare(
            NS(instances=[instance]), {"kind": "font_export", "options": options}, tmp_path
        )
