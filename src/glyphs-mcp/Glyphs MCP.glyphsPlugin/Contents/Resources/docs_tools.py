# encoding: utf-8

"""Documentation helper tools for Glyphs MCP.

The server's core value is live tool execution inside Glyphs. These tools are
helpers: they let clients search and fetch bundled reference docs on-demand so
the assistant can write more accurate code with fewer mistakes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcp_tools import mcp

logger = logging.getLogger(__name__)


DOC_BUNDLE_DIR = Path(__file__).resolve().parent / "MCP Documentation"
DOCS_DIRECTORY = DOC_BUNDLE_DIR / "docs"
INDEX_PATH = DOC_BUNDLE_DIR / "index.json"

DOCS_URI_PREFIX = "glyphs://glyphs-mcp/docs/"


def _load_index() -> Optional[Dict[str, Any]]:
    if not INDEX_PATH.exists():
        return None
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Unable to parse documentation index %s: %s", INDEX_PATH, exc)
        return None


def _index_documents(index: Dict[str, Any]) -> List[Dict[str, Any]]:
    docs = index.get("documents")
    if isinstance(docs, list):
        return [d for d in docs if isinstance(d, dict)]
    return []


def _normalize(text: str) -> str:
    return (text or "").strip().lower()


def _score_match(query: str, title: str, summary: str, path: str) -> float:
    q = _normalize(query)
    if not q:
        return 0.0

    t = _normalize(title)
    s = _normalize(summary)
    p = _normalize(path)

    # Prefer title hits, then summary, then path.
    score = 0.0
    if q == t:
        score = max(score, 10.0)
    if q in t:
        score = max(score, 8.0)
    if q in s:
        score = max(score, 5.0)
    if q in p:
        score = max(score, 3.0)
    return score


def _resolve_doc_path(doc_path: str) -> Optional[Path]:
    if not doc_path:
        return None

    candidate = (DOCS_DIRECTORY / doc_path).resolve()
    try:
        candidate.relative_to(DOCS_DIRECTORY.resolve())
    except ValueError:
        return None

    if candidate.is_file():
        return candidate
    return None


def _slice_text(text: str, offset: int, max_chars: int) -> Tuple[str, bool]:
    if offset < 0:
        offset = 0
    if max_chars <= 0:
        max_chars = 1

    end = min(len(text), offset + max_chars)
    chunk = text[offset:end]
    truncated = end < len(text)
    return chunk, truncated


@mcp.tool()
async def docs_search(query: str, max_results: int = 10) -> str:
    """Search bundled documentation by title/summary.

    Args:
        query: Search string (required).
        max_results: Max results to return (default: 10).

    Returns:
        JSON string with matches (id, title, summary, path, uri, score).
    """
    if not query.strip():
        return json.dumps(
            {
                "ok": False,
                "error": "Missing query",
                "hint": "Provide a search term, e.g. docs_search(query='GSFont').",
                "results": [],
            }
        )

    index = _load_index()
    if not index:
        return json.dumps(
            {
                "ok": False,
                "error": "Documentation index not available",
                "indexPath": str(INDEX_PATH),
                "results": [],
            }
        )

    docs = _index_documents(index)
    matches: List[Dict[str, Any]] = []
    for entry in docs:
        doc_id = entry.get("id") or ""
        path = entry.get("path") or ""
        title = entry.get("title") or ""
        summary = entry.get("summary") or ""

        score = _score_match(query, title, summary, path)
        if score <= 0:
            continue

        matches.append(
            {
                "id": doc_id,
                "title": title,
                "summary": summary,
                "path": path,
                "uri": f"{DOCS_URI_PREFIX}{path}" if path else None,
                "score": score,
            }
        )

    matches.sort(key=lambda r: (r.get("score", 0), r.get("title", "")), reverse=True)
    if max_results < 1:
        max_results = 1
    matches = matches[: min(max_results, 50)]

    return json.dumps(
        {
            "ok": True,
            "query": query,
            "count": len(matches),
            "results": matches,
        }
    )


@mcp.tool()
async def docs_get(
    doc_id: str = "",
    path: str = "",
    offset: int = 0,
    max_chars: int = 20000,
) -> str:
    """Fetch a bundled documentation page by id or path.

    Args:
        doc_id: Document id from index.json (e.g. "section_2").
        path: Document path from index.json (e.g. "section_2.rst").
        offset: Character offset into the file (default: 0).
        max_chars: Max characters to return (default: 20000).

    Returns:
        JSON string with content slice and paging metadata.
    """
    if not doc_id.strip() and not path.strip():
        return json.dumps(
            {
                "ok": False,
                "error": "Missing doc_id or path",
                "hint": "Use docs_search first, then call docs_get(doc_id=...) or docs_get(path=...).",
            }
        )

    index = _load_index()
    docs = _index_documents(index) if index else []

    chosen: Optional[Dict[str, Any]] = None
    if doc_id.strip():
        wanted = doc_id.strip()
        for entry in docs:
            if entry.get("id") == wanted:
                chosen = entry
                break

    if chosen is None and path.strip():
        wanted = path.strip()
        for entry in docs:
            if entry.get("path") == wanted:
                chosen = entry
                break

    doc_path = (chosen or {}).get("path") if chosen else path.strip()
    resolved = _resolve_doc_path(doc_path)
    if not resolved:
        return json.dumps(
            {
                "ok": False,
                "error": "Document not found",
                "docId": doc_id.strip() or None,
                "path": doc_path or None,
            }
        )

    raw = resolved.read_text(encoding="utf-8", errors="replace")
    chunk, truncated = _slice_text(raw, offset=offset, max_chars=max_chars)

    title = (chosen or {}).get("title")
    summary = (chosen or {}).get("summary")

    return json.dumps(
        {
            "ok": True,
            "docId": (chosen or {}).get("id") or (doc_id.strip() or None),
            "title": title,
            "summary": summary,
            "path": resolved.relative_to(DOCS_DIRECTORY).as_posix(),
            "uri": f"{DOCS_URI_PREFIX}{resolved.relative_to(DOCS_DIRECTORY).as_posix()}",
            "offset": max(offset, 0),
            "maxChars": max_chars,
            "totalChars": len(raw),
            "returnedChars": len(chunk),
            "truncated": truncated,
            "content": chunk,
            "nextOffset": (max(offset, 0) + len(chunk)) if truncated else None,
        }
    )


@mcp.tool()
async def docs_enable_page_resources() -> str:
    """Register each documentation page as its own MCP resource.

    This is optional: the recommended LLM flow is `docs_search` + `docs_get`.
    Enabling page resources can help clients that prefer `resources/read` URIs,
    but may "flood" some clients with hundreds of items in `resources/list`.

    Returns:
        JSON string with the number of newly-registered page resources.
    """
    try:
        import documentation_resources

        registered = documentation_resources.register_documentation_resources(register_pages=True)
        return json.dumps(
            {
                "ok": True,
                "registeredPages": registered,
                "note": (
                    "Per-page resources are now registered. Some MCP clients cache `resources/list`; "
                    "you may need to reconnect/refresh to see them."
                ),
            }
        )
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})
