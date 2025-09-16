# encoding: utf-8

"""Expose bundled Glyphs SDK documentation as MCP resources.

This module discovers the Sphinx-generated documentation that ships with the
plug-in and registers it with the shared ``FastMCP`` instance. The LLM can then
list and read pages using standard MCP resource calls.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

from fastmcp.resources import DirectoryResource, FileResource

from mcp_tools import mcp

logger = logging.getLogger(__name__)

# Location of the bundled documentation within the plug-in resources
DOC_BUNDLE_DIR = Path(__file__).resolve().parent / "MCP Documentation"
DOCS_DIRECTORY = DOC_BUNDLE_DIR / "docs"
INDEX_PATH = DOC_BUNDLE_DIR / "index.json"

_RESOURCE_PREFIX = "resource://glyphs-mcp/docs/"
_DIRECTORY_RESOURCE_URI = "resource://glyphs-mcp/docs"
_INDEX_RESOURCE_URI = "resource://glyphs-mcp/docs/index.json"

# Extensions that the Sphinx build commonly produces
_DOC_EXTENSIONS = (".html", ".htm", ".txt", ".md", ".json", ".fjson")
_MIME_BY_EXTENSION = {
    ".html": "text/html",
    ".htm": "text/html",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".fjson": "application/json",
}


def _load_index_data() -> Optional[Dict[str, Any]]:
    """Load the JSON index if it exists."""

    if not INDEX_PATH.exists():
        logger.debug("Documentation index not found at %s", INDEX_PATH)
        return None

    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.warning("Unable to parse documentation index %s: %s", INDEX_PATH, exc)
        return None


def _lookup_title(titles: Any, index: int, key: Optional[str]) -> Optional[str]:
    """Return a title from either a dict or list lookup table."""

    if isinstance(titles, dict) and key is not None:
        value = titles.get(key)
        if isinstance(value, str):
            return value

    if isinstance(titles, list) and 0 <= index < len(titles):
        value = titles[index]
        if isinstance(value, str):
            return value

    return None


def _coerce_entries(values: Iterable[Any], titles: Any, summaries: Any) -> List[Dict[str, Optional[str]]]:
    """Convert raw index entries into a uniform mapping."""

    entries: List[Dict[str, Optional[str]]] = []
    for position, item in enumerate(values):
        path: Optional[str] = None
        title: Optional[str] = None
        summary: Optional[str] = None

        if isinstance(item, str):
            path = item
            title = _lookup_title(titles, position, item)
            if isinstance(summaries, dict):
                summary = summaries.get(item)
            elif isinstance(summaries, list) and position < len(summaries):
                candidate = summaries[position]
                summary = candidate if isinstance(candidate, str) else None
        elif isinstance(item, dict):
            path = (
                item.get("path")
                or item.get("uri")
                or item.get("docname")
                or item.get("name")
                or item.get("file")
            )
            title = item.get("title") or item.get("name")
            summary = item.get("summary") or item.get("description") or item.get("excerpt")

        if path:
            entries.append({"path": path, "title": title, "summary": summary})

    return entries


def _extract_doc_entries(index_data: Dict[str, Any]) -> List[Dict[str, Optional[str]]]:
    """Extract document metadata from a Sphinx index structure."""

    candidate_keys = [
        "documents",
        "docnames",
        "pages",
        "files",
        "items",
        "sections",
        "toctree",
    ]

    titles = index_data.get("titles")
    summaries = (
        index_data.get("summaries")
        or index_data.get("descriptions")
        or index_data.get("abstracts")
    )

    for key in candidate_keys:
        value = index_data.get(key)
        if isinstance(value, list) and value:
            entries = _coerce_entries(value, titles, summaries)
            if entries:
                return entries

    # Fallback: search the first list of strings/dicts in the index
    for value in index_data.values():
        if isinstance(value, list) and value and all(isinstance(v, (str, dict)) for v in value):
            entries = _coerce_entries(value, titles, summaries)
            if entries:
                return entries

    return []


def _guess_mime(path: Path) -> str:
    """Return an appropriate MIME type for a documentation asset."""

    return _MIME_BY_EXTENSION.get(path.suffix.lower(), "text/plain")


def _candidate_relatives(raw_path: str) -> List[Path]:
    """Generate possible relative paths for an index entry."""

    relative = Path(raw_path.strip())
    candidates: List[Path] = [relative]

    if not relative.suffix:
        for extension in _DOC_EXTENSIONS:
            candidates.append(relative.with_suffix(extension))
        candidates.append(relative / "index.html")
        candidates.append(relative / "index.fjson")

    # When the index already contains a docs/ prefix ensure we also try without it
    if relative.parts and relative.parts[0] == "docs":
        without_prefix = Path(*relative.parts[1:])
        candidates.append(without_prefix)

    # Deduplicate while preserving order
    seen: set[Path] = set()
    unique_candidates: List[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            unique_candidates.append(candidate)
            seen.add(candidate)

    return unique_candidates


def _resolve_document_path(raw_path: str) -> Optional[Path]:
    """Resolve a documentation entry to an on-disk file within the bundle."""

    for candidate in _candidate_relatives(raw_path):
        for base in (DOCS_DIRECTORY, DOC_BUNDLE_DIR):
            candidate_path = (base / candidate).resolve()
            try:
                candidate_path.relative_to(DOC_BUNDLE_DIR)
            except ValueError:
                continue

            if candidate_path.is_file():
                return candidate_path

    logger.debug("No file found for documentation entry '%s'", raw_path)
    return None


def _register_directory_listing() -> None:
    """Register a directory resource that lists available documentation files."""

    try:
        mcp.add_resource(
            DirectoryResource(
                uri=_DIRECTORY_RESOURCE_URI,
                name="Glyphs SDK documentation",
                description="Listing of the bundled Glyphs SDK ObjectWrapper documentation.",
                path=DOCS_DIRECTORY.resolve(),
                recursive=True,
                pattern="*",
                mime_type="application/json",
                tags={"documentation", "glyphs-sdk"},
            )
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.warning("Failed to register documentation directory resource: %s", exc)


def _register_index_file() -> None:
    """Register the JSON index as a resource for programmatic access."""

    if not INDEX_PATH.exists():
        return

    try:
        mcp.add_resource(
            FileResource(
                uri=_INDEX_RESOURCE_URI,
                name="Glyphs SDK documentation index",
                description="Machine-readable manifest for the packaged Glyphs SDK documentation.",
                path=INDEX_PATH.resolve(),
                mime_type="application/json",
                tags={"documentation", "glyphs-sdk"},
            )
        )
    except Exception as exc:  # pragma: no cover - defensive logging only
        logger.warning("Failed to register documentation index resource: %s", exc)


def _register_document_pages(index_entries: List[Dict[str, Optional[str]]]) -> None:
    """Register each documentation page as an individual resource."""

    seen_uris: set[str] = set()
    docs_root = DOCS_DIRECTORY.resolve()

    for entry in index_entries:
        raw_path = entry.get("path")
        if not raw_path:
            continue

        resolved = _resolve_document_path(raw_path)
        if not resolved:
            continue

        try:
            relative = resolved.relative_to(docs_root)
        except ValueError:
            # Skip files outside the docs directory (e.g., the index JSON)
            continue

        uri_suffix = quote(relative.as_posix())
        resource_uri = f"{_RESOURCE_PREFIX}{uri_suffix}"
        if resource_uri in seen_uris:
            continue

        title = entry.get("title") or relative.stem.replace("_", " ").title()
        summary = entry.get("summary")
        description = summary or f"Documentation page {relative.as_posix()} from the Glyphs SDK ObjectWrapper."

        try:
            mcp.add_resource(
                FileResource(
                    uri=resource_uri,
                    name=title,
                    description=description,
                    path=resolved,
                    mime_type=_guess_mime(resolved),
                    tags={"documentation", "glyphs-sdk"},
                )
            )
        except Exception as exc:  # pragma: no cover - defensive logging only
            logger.warning("Failed to register documentation page %s: %s", resolved, exc)
            continue

        seen_uris.add(resource_uri)

    if not seen_uris:
        logger.info(
            "Documentation index present but no individual pages were registered. "
            "Check that the Sphinx build output is located in %s.",
            DOCS_DIRECTORY,
        )


def register_documentation_resources() -> None:
    """Discover bundled documentation and register MCP resources."""

    if not DOCS_DIRECTORY.exists():
        logger.info("Documentation directory %s not found; skipping registration", DOCS_DIRECTORY)
        return

    _register_directory_listing()
    _register_index_file()

    index_data = _load_index_data()
    entries: List[Dict[str, Optional[str]]] = []
    if index_data:
        entries = _extract_doc_entries(index_data)

    if not entries:
        # Fallback: register all HTML-like files in the docs folder
        entries = [
            {
                "path": path.relative_to(DOCS_DIRECTORY).as_posix(),
                "title": path.stem.replace("_", " ").title(),
                "summary": None,
            }
            for path in sorted(DOCS_DIRECTORY.rglob("*"))
            if path.is_file()
        ]

    _register_document_pages(entries)


# Automatically register the resources when the plug-in imports this module
register_documentation_resources()

