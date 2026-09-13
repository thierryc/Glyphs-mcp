#!/usr/bin/env python3
"""Read the installed Glyphs 4 corpus locally. No Glyphs, MCP or network imports."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

CORPUS = Path(__file__).resolve().parents[1] / "assets/knowledge"
STOP_WORDS = set("a an and are as at be by can do does for from how i in into is it its my of on or that the their this to when which with without".split())


class DocsError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def unavailable(message):
    return DocsError("update_required", message + "; update the installed Glyphs 4 development skill through the existing installer.")


def load(corpus=CORPUS):
    try:
        raw = (corpus / "index.json").read_bytes()
        manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Invalid corpus manifest")
        if manifest.get("schemaVersion") != 1 or manifest.get("applicationTarget") != "4":
            raise ValueError("Unsupported corpus manifest")
        if hashlib.sha256(raw).hexdigest() != manifest["indexSha256"]:
            raise ValueError("Documentation index checksum mismatch")
        index = json.loads(raw)
        if not isinstance(index, dict):
            raise ValueError("Invalid documentation index")
        if index.get("schemaVersion") != 1 or index.get("applicationTarget") != "4":
            raise ValueError("Unsupported documentation index")
        revision = manifest["sourceRevision"]
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Invalid pinned source revision")
        if index["sourceRevision"] != revision:
            raise ValueError("Documentation source revisions differ")
        rows = index["documents"]
        for row in rows:
            if not all(isinstance(row.get(k), str) for k in ("id", "path", "title", "summary", "checksum")):
                raise ValueError("Invalid documentation record")
            if row.get("symbol") is not None and not isinstance(row["symbol"], str):
                raise ValueError("Invalid native symbol")
            for key in ("sourcePath", "sourceUrl", "sourceKind", "sourceChecksum", "applicationTarget", "nativeVerification"):
                if not isinstance(row.get(key), str) or not row[key]:
                    raise ValueError("Missing or invalid provenance: " + key)
            if row["applicationTarget"] != "4" or not re.fullmatch(r"[0-9a-f]{64}", row["sourceChecksum"]):
                raise ValueError("Invalid documentation provenance")
            # The handbook snapshot has no known upstream revision. SDK sources
            # must agree with the pinned index; missing evidence is not a pin.
            expected_revision = None if row["sourceKind"] == "glyphs-handbook" else revision
            if "sourceRevision" not in row or row["sourceRevision"] != expected_revision:
                raise ValueError("Invalid source revision for " + row["id"])
            if not isinstance(row.get("searchTerms"), list) or not all(isinstance(t, str) for t in row["searchTerms"]):
                raise ValueError("Invalid search terms")
        ids = [r["id"] for r in rows]
        paths = [r["path"] for r in rows]
        if len(ids) != len(set(ids)) or len(paths) != len(set(paths)) or not rows:
            raise ValueError("Duplicate or empty documentation index")
        if {r["path"]: r["checksum"] for r in rows} != manifest["documents"]:
            raise ValueError("Documentation manifest and index differ")
        return rows, manifest
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise unavailable("Offline documentation unavailable: " + str(exc)) from exc


def read(row, corpus=CORPUS):
    try:
        root = (corpus / "docs").resolve()
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid indexed path")
        path = (root / relative).resolve()
        path.relative_to(root)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row["checksum"]:
            raise ValueError("Documentation file checksum mismatch: " + row["id"])
        return data.decode("utf-8")
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        raise unavailable(str(exc)) from exc


def metadata(row):
    return {key: row.get(key) for key in ("id", "title", "summary", "path", "symbol",
            "sourcePath", "sourceRevision", "sourceLine", "sourceUrl", "sourceKind",
            "sourceChecksum", "checksum", "applicationTarget", "formatVersion", "nativeVerification")}


def tokens(text):
    return set(re.findall(r"[a-z0-9_]+", text.lower())) - STOP_WORDS


def score(query, row, corpus=CORPUS):
    # Keep exact symbols/paths decisive. For questions, favor coverage across
    # meaningful titles, summaries and body terms over repeated directory names.
    # Ranking is lexical relevance, never evidence of native compatibility.
    q = query.lower().strip()
    terms = tokens(query)
    if not terms:
        return 0
    path = Path(row["path"])
    source_file = row["sourceKind"] == "glyphs-sdk-source"
    guide = path.suffix.lower() in (".md", ".rst", ".txt") or path.name in ("README", "LICENSE")
    title = path.name if source_file and not guide else row["title"]
    # Split native camel-case names for retrieval without changing their owner.
    native_title = title + " " + (row.get("symbol") or "")
    title_terms = tokens(native_title) | tokens(re.sub(r"([a-z])([A-Z])", r"\1 \2", native_title))
    summary_terms = tokens(row["summary"])
    body_terms = set(row["searchTerms"]) | tokens(row["title"])
    coverage = len(terms & (title_terms | summary_terms | body_terms)) / len(terms)
    value = (8 * len(terms & title_terms) + 6 * len(terms & summary_terms)
             + 4 * len(terms & body_terms)) * (0.5 + coverage)
    if source_file and not guide:
        value *= 0.5
    identities = (row["title"], row.get("symbol") or "", row["id"], row["path"], row["sourcePath"])
    if q in (identity.lower() for identity in identities):
        value += 1000
    native = re.fullmatch(r"([a-z_]\w*)(?:\.([a-z_]\w*))?(?:\(\))?", q)
    if native:
        owner, member = native.groups()
        # A qualified method's exact token must outweigh generic owner matches.
        # A guide is eligible only when its primary example actually inherits
        # the requested class; later examples may describe other plugin types.
        owns_symbol = (row.get("symbol") or "").lower().startswith(owner + ".")
        owns_template = False
        if (source_file and guide and "Python Templates" in path.parts
                and owner in body_terms and (not member or member in body_terms)):
            declaration = re.search(r"(?m)^\s*class\s+\w+\s*\(\s*(\w+)\s*\)\s*:", read(row, corpus))
            owns_template = bool(declaration and declaration.group(1).lower() == owner)
        if (member and member in (title_terms | summary_terms | body_terms)
                and (owns_symbol or owns_template)) or (not member and owns_template):
            value += 60
    return value


def search(query, limit=5, corpus=CORPUS):
    if not query.strip() or not tokens(query) or limit < 1:
        raise DocsError("invalid_request", "Provide a search query and a positive limit.")
    rows, manifest = load(corpus)
    matches = [(score(query, r, corpus), r) for r in rows]
    matches = sorted((pair for pair in matches if pair[0] > 0), key=lambda p: (-p[0], p[1]["id"]))
    selected = matches[:min(limit, 20)]
    for _, row in selected:
        read(row, corpus)  # Never return a missing/corrupt result as usable evidence.
    return dict(ok=True, query=query, totalCount=len(matches), returnedCount=len(selected),
                complete=len(selected) == len(matches), sourceRevision=manifest["sourceRevision"],
                results=[dict(metadata(r), score=round(s, 3)) for s, r in selected])


def get(doc_id, offset=0, max_chars=4000, corpus=CORPUS):
    if offset < 0 or max_chars < 1:
        raise DocsError("invalid_request", "Offset must be nonnegative and max-chars positive.")
    rows, _ = load(corpus)
    row = next((r for r in rows if r["id"] == doc_id), None)
    if row is None:
        raise DocsError("document_not_found", "Unknown documentation ID; use local docs search. This is not a font document ID.")
    content = read(row, corpus)
    if offset > len(content):
        raise DocsError("invalid_request", "Offset is beyond the end of this documentation page.")
    limit = min(max_chars, 12000)
    chunk = content[offset:offset + limit]
    end = offset + len(chunk)
    return dict(ok=True, **metadata(row), content=chunk, offset=offset,
                totalChars=len(content), returnedChars=len(chunk),
                complete=offset == 0 and end == len(content), truncated=end < len(content),
                nextOffset=end if end < len(content) else None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("search")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=5)
    fetch = commands.add_parser("get")
    fetch.add_argument("id")
    fetch.add_argument("--offset", type=int, default=0)
    fetch.add_argument("--max-chars", type=int, default=4000)
    args = parser.parse_args(argv)
    try:
        result = search(args.query, args.limit) if args.command == "search" else get(args.id, args.offset, args.max_chars)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except DocsError as exc:
        print(json.dumps(dict(ok=False, error=dict(code=exc.code, message=str(exc))), ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
