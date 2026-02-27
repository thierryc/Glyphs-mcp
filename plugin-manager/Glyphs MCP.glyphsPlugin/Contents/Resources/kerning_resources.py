# encoding: utf-8

"""Register bundled kerning datasets as MCP resources."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastmcp.resources import DirectoryResource, FileResource

from mcp_tools import mcp

logger = logging.getLogger(__name__)

_KERNING_DIR_URI = "glyphs://glyphs-mcp/kerning"
_RESOURCE_BASE = Path(__file__).resolve().parent / "kerning_data"

_AF_BASE_URI = "glyphs://glyphs-mcp/kerning/andre-fuchs"
_AF_DIR = _RESOURCE_BASE / "andre_fuchs"
_AF_RELEVANT_PATH = _AF_DIR / "relevant_pairs.v1.json"
_AF_ATTR_PATH = _AF_DIR / "ATTRIBUTION.md"


def register_kerning_resources() -> None:
    """Register directory + a small set of curated kerning dataset resources."""

    if not _RESOURCE_BASE.exists():
        logger.info("Kerning data directory %s not found; skipping kerning resource registration", _RESOURCE_BASE)
        return

    try:
        mcp.add_resource(
            DirectoryResource(
                uri=_KERNING_DIR_URI,
                name="Kerning datasets",
                description="Bundled kerning datasets and metadata (offline).",
                path=_RESOURCE_BASE.resolve(),
                recursive=True,
                pattern="*",
                mime_type="application/json",
                tags={"kerning", "dataset", "glyphs-mcp"},
            )
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.warning("Failed to register kerning directory resource: %s", exc)

    if _AF_RELEVANT_PATH.exists():
        try:
            mcp.add_resource(
                FileResource(
                    uri=_AF_BASE_URI + "/relevant_pairs.v1.json",
                    name="Andre Fuchs relevant kerning pairs (normalized)",
                    description="Normalized snapshot of relevance-ranked kerning pairs (MIT).",
                    path=_AF_RELEVANT_PATH.resolve(),
                    mime_type="application/json",
                    tags={"kerning", "dataset", "andre-fuchs"},
                )
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to register Andre-Fuchs dataset resource: %s", exc)

    if _AF_ATTR_PATH.exists():
        try:
            mcp.add_resource(
                FileResource(
                    uri=_AF_BASE_URI + "/ATTRIBUTION.md",
                    name="Andre Fuchs kerning pairs attribution",
                    description="Attribution and normalization notes for the bundled kerning pairs dataset.",
                    path=_AF_ATTR_PATH.resolve(),
                    mime_type="text/markdown",
                    tags={"kerning", "dataset", "andre-fuchs", "attribution"},
                )
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to register Andre-Fuchs attribution resource: %s", exc)


if os.environ.get("GLYPHS_MCP_SKIP_AUTO_REGISTER") != "1":
    register_kerning_resources()
