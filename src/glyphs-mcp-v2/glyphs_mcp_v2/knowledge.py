"""Deterministic offline search over the pinned Glyphs MCP Knowledge corpus."""

from __future__ import annotations

import copy
import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .semantic import fingerprint_model


_TOKEN = re.compile(r"[A-Za-z0-9_.+-]+")
_INDEX = Path(__file__).with_name("knowledge_data") / "index.json"


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(token.lower() for token in _TOKEN.findall(value) if len(token) > 1)


@lru_cache(maxsize=1)
def load_corpus() -> Mapping[str, Any]:
    try:
        value = json.loads(_INDEX.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("the pinned Knowledge corpus is unavailable") from exc
    manifest = value.get("manifest")
    entries = value.get("entries")
    if not isinstance(manifest, Mapping) or not isinstance(entries, list):
        raise RuntimeError("the pinned Knowledge corpus is invalid")
    if int(manifest.get("entryCount") or -1) != len(entries):
        raise RuntimeError("the pinned Knowledge manifest does not match its entries")
    return value


def knowledge_manifest() -> dict[str, Any]:
    corpus = load_corpus()
    manifest = copy.deepcopy(dict(corpus["manifest"]))
    manifest["corpusFingerprint"] = fingerprint_model(corpus)
    return manifest


def _filtered(
    entries: Sequence[Mapping[str, Any]],
    *,
    topics: Sequence[str],
    authorities: Sequence[str],
    glyphs_versions: Sequence[str],
) -> list[Mapping[str, Any]]:
    topic_set = set(topics)
    authority_set = set(authorities)
    version_set = set(glyphs_versions)
    return [
        entry
        for entry in entries
        if (not topic_set or topic_set.intersection(entry.get("topics") or ()))
        and (not authority_set or str(entry.get("authority") or "") in authority_set)
        and (not version_set or version_set.intersection(entry.get("glyphsVersions") or ()))
    ]


def _snippet(body: str, query_tokens: Sequence[str], *, limit: int = 600) -> str:
    normalized = re.sub(r"\s+", " ", body).strip()
    lowered = normalized.lower()
    offsets = [lowered.find(token) for token in query_tokens if lowered.find(token) >= 0]
    start = max(0, min(offsets) - 120) if offsets else 0
    end = min(len(normalized), start + limit)
    value = normalized[start:end]
    if start:
        value = "…" + value
    if end < len(normalized):
        value += "…"
    return value


def search_knowledge(
    query: str,
    *,
    topics: Sequence[str] = (),
    authorities: Sequence[str] = (),
    glyphs_versions: Sequence[str] = (),
) -> dict[str, Any]:
    text = str(query or "").strip()
    if not text:
        raise ValueError("query is required")
    query_tokens = _tokens(text)
    if not query_tokens:
        raise ValueError("query must contain searchable terms")
    corpus = load_corpus()
    entries = _filtered(
        corpus["entries"],
        topics=topics,
        authorities=authorities,
        glyphs_versions=glyphs_versions,
    )
    document_frequency = Counter()
    entry_tokens: dict[str, tuple[str, ...]] = {}
    for entry in entries:
        tokens = _tokens(
            " ".join(
                (
                    str(entry.get("title") or ""),
                    " ".join(entry.get("keywords") or ()),
                    " ".join(entry.get("topics") or ()),
                    str(entry.get("body") or ""),
                )
            )
        )
        entry_tokens[str(entry["id"])] = tokens
        document_frequency.update(set(tokens))
    scored: list[tuple[float, Mapping[str, Any]]] = []
    total = max(1, len(entries))
    phrase = text.lower()
    for entry in entries:
        identity = str(entry["id"])
        tokens = entry_tokens[identity]
        frequencies = Counter(tokens)
        title = str(entry.get("title") or "").lower()
        keywords = {str(value).lower() for value in entry.get("keywords") or ()}
        topics_value = {str(value).lower() for value in entry.get("topics") or ()}
        score = 0.0
        for token in query_tokens:
            tf = frequencies[token]
            if not tf:
                continue
            inverse = math.log(1 + total / (1 + document_frequency[token]))
            score += (1 + math.log(tf)) * inverse
            if token in title:
                score += 8
            if any(token in keyword for keyword in keywords):
                score += 5
            if token in topics_value:
                score += 4
        if phrase in title:
            score += 14
        elif phrase in str(entry.get("body") or "").lower():
            score += 6
        if score <= 0:
            continue
        scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], str(item[1]["id"])))
    items = [
        {
            "id": entry["id"],
            "title": entry["title"],
            "summary": entry["summary"],
            "snippet": _snippet(str(entry.get("body") or ""), query_tokens),
            "topics": list(entry.get("topics") or ()),
            "glyphsVersions": list(entry.get("glyphsVersions") or ()),
            "authority": entry.get("authority"),
            "sourceUrl": entry.get("sourceUrl"),
            "sourcePath": entry.get("sourcePath"),
            "sourceRevision": entry.get("sourceRevision"),
            "verifiedAt": entry.get("verifiedAt"),
            "contentFingerprint": entry.get("contentFingerprint"),
            "score": round(score, 6),
        }
        for score, entry in scored
    ]
    return {
        "query": text,
        "filters": {
            "topics": list(topics),
            "authorities": list(authorities),
            "glyphsVersions": list(glyphs_versions),
        },
        "matchCount": len(items),
        "items": items,
        "manifest": knowledge_manifest(),
    }


def get_knowledge(entry_ids: Sequence[str]) -> dict[str, Any]:
    ids = tuple(dict.fromkeys(str(value) for value in entry_ids if str(value)))
    if not ids:
        raise ValueError("entryIds requires at least one Knowledge ID")
    if len(ids) > 20:
        raise ValueError("entryIds accepts at most 20 Knowledge IDs")
    corpus = load_corpus()
    index = {str(entry["id"]): entry for entry in corpus["entries"]}
    missing = [identity for identity in ids if identity not in index]
    items = [copy.deepcopy(dict(index[identity])) for identity in ids if identity in index]
    return {
        "requestedCount": len(ids),
        "foundCount": len(items),
        "missingIds": missing,
        "items": items,
        "manifest": knowledge_manifest(),
    }


__all__ = [
    "get_knowledge",
    "knowledge_manifest",
    "load_corpus",
    "search_knowledge",
]
