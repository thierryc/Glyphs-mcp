"""Explicit width scope at the worker and public MCP boundaries."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_simple_v2_sidecar import native_worker, service


def payload(names, delta=17):
    return {"jobId": "job_test", "document": {"id": "doc_1", "path": "/tmp/font.glyphs", "generation": 3},
            "source": "/tmp/source.glyphs", "sourceHash": "sha256:" + "a" * 64,
            "request": {"kind": "width_delta", "delta": delta, "glyphs": names}}


@pytest.mark.parametrize("names", [["missing"], ["A", "missing"], ["zMissing", "A", "aMissing"]])
def test_missing_names_fail_before_any_layer_is_examined(monkeypatch, names):
    class Glyph:
        name = "A"

        @property
        def layers(self):
            pytest.fail("Must validate the complete explicit selection before reading layers")

    monkeypatch.setattr(native_worker, "_load_font", lambda _: SimpleNamespace(glyphs=[Glyph()]))
    with pytest.raises(ValueError) as error:
        native_worker.build_patch(payload(names))
    assert str(error.value) == "width_delta requested glyphs missing from saved source: " + json.dumps(sorted(set(names) - {"A"}))


@pytest.mark.parametrize("names,expected", [(["A"], ["A", "A"]), ([], ["A", "A", "B"])])
def test_valid_and_omitted_scope_keep_stored_layers_and_fractional_arithmetic(monkeypatch, names, expected):
    layers = [SimpleNamespace(layerId=key, associatedMasterId="M1", width=600.125) for key in ("M1", "BACKUP", "M2")]
    font = SimpleNamespace(glyphs=[SimpleNamespace(name="A", layers=layers[:2]), SimpleNamespace(name="B", layers=layers[2:])])
    monkeypatch.setattr(native_worker, "_load_font", lambda _: font)
    result = native_worker.build_patch(payload(names, .375))
    assert [c["glyph"] for c in result["changes"]] == expected
    assert result["changes"][1]["layer"] == "BACKUP"
    assert all(c["before"] == 600.125 and c["after"] == 600.5 for c in result["changes"])
    assert all(layer.width == 600.125 for layer in layers), "Preparation must not write the native font"


def test_public_mcp_rejects_boolean_and_never_publishes_partial_missing_scope(tmp_path, monkeypatch):
    from fastmcp import Client
    from glyphs_mcp_sidecar.server import create_server

    value, bridge, _ = service(tmp_path)
    calls = []
    layer = SimpleNamespace(layerId="M1", associatedMasterId="M1", width=600.125)
    monkeypatch.setattr(native_worker, "_load_font", lambda _: SimpleNamespace(glyphs=[SimpleNamespace(name="A", layers=[layer])]))

    def prepare(job_root, document, request, source_path, fingerprint, cancel):
        calls.append(request)
        return native_worker.build_patch({"jobId": job_root.name, "document": document,
                                         "request": request, "source": str(source_path), "sourceHash": fingerprint})

    value.worker = SimpleNamespace(prepare=prepare)

    def body(result):
        return result.structuredContent or json.loads(result.content[0].text)

    async def exercise():
        async with Client(create_server(value)) as client:
            assert len(await client.list_tools()) == 7
            for boolean in (True, False):
                response = await client.call_tool_mcp("start_job", {"document_id": "doc_1", "kind": "width_delta", "glyphs": ["A"], "delta": boolean})
                assert response.isError is True  # MCP schema rejection, not service error.code.
                assert not calls and not value.jobs.records()
            for names in (["missing"], ["A", "missing"]):
                start = body(await client.call_tool_mcp("start_job", {"document_id": "doc_1", "kind": "width_delta", "glyphs": names, "delta": 17}))
                job_id = start["data"]["id"]
                for _ in range(100):
                    job = body(await client.call_tool_mcp("get_job", {"job_id": job_id}))["data"]
                    if job["status"] == "failed":
                        break
                    await asyncio.sleep(.01)
                assert job["status"] == "failed"
                assert job["error"]["code"] == "job_failed"
                assert 'missing from saved source: ["missing"]' in job["error"]["message"]
                assert job["changeCount"] == 0 and job["sample"] == []
                assert not (value.jobs.path(job_id) / "patch.json").exists()
                rejected = body(await client.call_tool_mcp("apply_job", {"job_id": job_id}))
                assert rejected["ok"] is False and bridge.patch is None
            assert layer.width == 600.125
    try:
        asyncio.run(exercise())
    finally:
        value.close()
