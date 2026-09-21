"""Contracts for the reset v2 protocol."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[3]
for root in (REPO / "src" / "protocol", REPO / "src" / "bridge"):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from glyphs_mcp_bridge.companions import CompanionRegistry  # noqa: E402
from glyphs_mcp_protocol import (  # noqa: E402
    TOOL_NAMES,
    ProtocolError,
    outline_hash,
    validate_patch,
)


def patch() -> dict:
    return {
        "version": 1,
        "jobId": "job_1",
        "documentId": "doc_1",
        "sourcePath": "/tmp/Test.glyphs",
        "sourceHash": "sha256:" + "a" * 64,
        "generation": 4,
        "changes": [
            {
                "kind": "set",
                "glyph": "A",
                "layer": "M1",
                "field": "width",
                "before": 600,
                "after": 608,
            }
        ],
        "summary": "Add 8 units to A",
    }


def test_public_surface_is_exactly_nine_small_tools() -> None:
    assert TOOL_NAMES == (
        "get_status",
        "list_documents",
        "read_entities",
        "start_job",
        "get_job",
        "apply_job",
        "accept_job",
        "discard_job",
        "save_document",
    )


def test_patch_is_closed_and_normalized() -> None:
    assert validate_patch(patch()) == patch()
    invalid = patch()
    invalid["candidateFingerprint"] = "obsolete"
    with pytest.raises(ProtocolError, match="unexpected fields"):
        validate_patch(invalid)


def test_patch_rejects_duplicate_targets_and_unbounded_fields() -> None:
    invalid = patch()
    invalid["changes"].append(dict(invalid["changes"][0], after=616))
    with pytest.raises(ProtocolError, match="duplicate target"):
        validate_patch(invalid)
    invalid = patch()
    invalid["changes"][0]["field"] = "completeFontModel"
    with pytest.raises(ProtocolError) as caught:
        validate_patch(invalid)
    assert caught.value.code == "unsupported_change"


def test_translate_uses_only_target_outline_hashes() -> None:
    value = patch()
    before = outline_hash([(0, 0, "line"), (10, 20, "curve")])
    after = outline_hash([(3, 4, "line"), (13, 24, "curve")])
    value["changes"] = [
        {
            "kind": "translate",
            "glyph": "A",
            "layer": "M1",
            "dx": 3,
            "dy": 4,
            "beforeHash": before,
            "afterHash": after,
        }
    ]
    assert validate_patch(value)["changes"][0]["beforeHash"] == before


def test_companion_registration_is_idempotent_and_failure_isolated() -> None:
    registry = CompanionRegistry()
    manifest = {
        "protocol": 1,
        "id": "curve-inspector",
        "version": "1.0.0",
        "capabilities": ["curve.measure", "curve.measure"],
    }
    assert registry.register(manifest) is True
    assert registry.register(manifest) is False
    assert registry.register({"protocol": 99}) is False
    assert registry.list() == [
        {
            "protocol": 1,
            "id": "curve-inspector",
            "version": "1.0.0",
            "capabilities": ["curve.measure"],
        }
    ]
