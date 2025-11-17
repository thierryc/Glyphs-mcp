#!/usr/bin/env python3
"""Generate reStructuredText files and metadata for the MCP server.

The script extracts triple-quoted documentation blocks from
``GlyphsApp/__init__.py``. Each block is written to a
``section_*.rst`` file inside ``docs/`` (ignored by Git) and recorded in
``index.json`` for lightweight lookup.  It also produces concise titles
and summaries that the MCP resource list can expose to the LLM and
caches those summaries in ``summaries.json`` so unchanged sections do not
need to be reprocessed.
"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List


SummaryCache = Dict[str, Dict[str, str]]


SUMMARY_CACHE_FILENAME = "summaries.json"
SUMMARY_CACHE_VERSION = 2
SKIP_BLOCK_DIRECTIVES = {
    "code-block",
    "autosummary",
    "image",
    "figure",
    "seealso",
}


def extract_sections(init_path: Path) -> list[str]:
    """Return a list of documentation sections from ``init_path``."""

    content = init_path.read_text(encoding="utf-8")
    return [part.strip() for part in re.findall(r"'''(.*?)'''", content, re.DOTALL)]


def _looks_like_heading(line: str, underline: str) -> bool:
    underline = underline.strip()
    if not line or not underline:
        return False
    if len(underline) < len(line):
        return False
    return len(set(underline)) == 1


DIRECTIVE_RE = re.compile(r"^\.\.\s+(?P<role>\w+)::\s*(?P<target>.+)$")
ROLE_LINE_RE = re.compile(r"^:(?P<role>\w+):`(?P<target>[^`]+)`$")
INLINE_ROLE_RE = re.compile(r":(?P<role>\w+):`(?P<target>[^`]+)`")
DOUBLE_BACKTICK_RE = re.compile(r"``([^`]+)``")


def _clean_text(text: str) -> str:
    """Remove the most common reST inline markup."""

    def _inline_repl(match: re.Match[str]) -> str:
        return match.group("target")

    cleaned = INLINE_ROLE_RE.sub(_inline_repl, text)
    cleaned = DOUBLE_BACKTICK_RE.sub(r"\1", cleaned)
    cleaned = cleaned.replace("`", "")
    return " ".join(cleaned.split())


def derive_title(section: str) -> str:
    """Best-effort summary of the section heading."""

    lines = textwrap.dedent(section).strip().splitlines()
    # Prefer explicit headings (text line followed by ===== underline)
    for i in range(len(lines) - 1):
        candidate = lines[i].strip()
        underline = lines[i + 1]
        if candidate and _looks_like_heading(candidate, underline):
            return _clean_text(candidate)

    # Fall back to directive-based titles
    for raw in lines:
        stripped = raw.strip()
        match = DIRECTIVE_RE.match(stripped)
        if match:
            target = _clean_text(match.group("target"))
            role = match.group("role")
            if target:
                return f"{target} ({role})"

        match = ROLE_LINE_RE.match(stripped)
        if match:
            target = _clean_text(match.group("target"))
            role = match.group("role")
            if target:
                return f"{target} ({role})"

    # Otherwise use the first non-empty line
    for raw in lines:
        stripped = _clean_text(raw.strip())
        if stripped:
            return stripped

    return "Untitled section"


def _iter_plaintext_lines(lines: Iterable[str]) -> Iterable[str]:
    """Yield non-directive lines suitable for summary extraction."""

    skip_block = False
    for line in lines:
        if skip_block:
            if line.startswith((" ", "\t")) or not line.strip():
                continue
            skip_block = False

        stripped = line.strip()
        if not stripped:
            yield ""
            continue

        if stripped.startswith(".. "):
            directive_name = stripped[3:].split("::", 1)[0].strip()
            if directive_name in SKIP_BLOCK_DIRECTIVES:
                skip_block = True
                continue
            # Skip the directive line itself but keep its descriptive body
            continue

        if stripped.startswith(":") and ":" in stripped[1:]:
            # Field list or inline role definition
            continue

        if len(set(stripped)) == 1 and stripped[0] in "=-~`^'\"*+#_":
            # Heading underline or separator
            continue

        yield stripped


def _strip_leading_heading(section: str) -> List[str]:
    lines = textwrap.dedent(section).splitlines()
    for i in range(len(lines) - 1):
        candidate = lines[i].strip()
        underline = lines[i + 1]
        if candidate and _looks_like_heading(candidate, underline):
            return lines[i + 2 :]
    return lines


def summarize_section(section: str) -> str:
    """Return a short textual summary for the section."""

    body_lines = _strip_leading_heading(section)
    lines = []
    for line in _iter_plaintext_lines(body_lines):
        if not line:
            if lines:
                break
            continue
        lines.append(_clean_text(line))

    if not lines:
        return ""

    paragraph = " ".join(lines)
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    if not sentences:
        return paragraph

    summary = " ".join(sentences[:2]).strip()
    return summary or paragraph


def load_summary_cache(path: Path) -> SummaryCache:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_summary_cache(path: Path, cache: SummaryCache) -> None:
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def find_init_file(root: Path) -> Path:
    """Locate ``GlyphsApp/__init__.py`` relative to the documentation folder."""

    candidates = [root.parent / "GlyphsApp" / "__init__.py"]

    for ancestor in root.parents:
        glyphs_sdk = ancestor / "GlyphsSDK" / "ObjectWrapper" / "GlyphsApp" / "__init__.py"
        candidates.append(glyphs_sdk)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise SystemExit("Unable to locate GlyphsApp/__init__.py")


def generate_docs() -> None:
    """Write section files into ``docs/`` and accompanying metadata."""

    root = Path(__file__).resolve().parent
    init_file = find_init_file(root)
    sections = extract_sections(init_file)
    if not sections:
        raise SystemExit("No documentation blocks found")

    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    cache_path = root / SUMMARY_CACHE_FILENAME
    existing_cache = load_summary_cache(cache_path)
    new_cache: SummaryCache = {}
    documents: List[Dict[str, str]] = []

    for i, section in enumerate(sections, start=1):
        name = f"section_{i}"
        rel_path = f"{name}.rst"
        checksum = hashlib.sha1(section.encode("utf-8")).hexdigest()

        (docs_dir / rel_path).write_text(section + "\n", encoding="utf-8")

        cached_entry = existing_cache.get(rel_path)
        if (
            cached_entry
            and cached_entry.get("checksum") == checksum
            and cached_entry.get("version") == SUMMARY_CACHE_VERSION
        ):
            summary = cached_entry.get("summary", "")
        else:
            summary = summarize_section(section)

        title = derive_title(section)
        if not summary:
            summary = title

        new_cache[rel_path] = {
            "checksum": checksum,
            "summary": summary,
            "version": SUMMARY_CACHE_VERSION,
        }

        documents.append(
            {
                "id": name,
                "path": rel_path,
                "title": title,
                "summary": summary,
                "checksum": checksum,
            }
        )

    index_payload = {
        "version": 2,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "documents": documents,
        "titles": {doc["id"]: doc["title"] for doc in documents},
    }

    (root / "index.json").write_text(
        json.dumps(index_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    save_summary_cache(cache_path, new_cache)
    print(f"Wrote {len(sections)} sections, index.json, and {SUMMARY_CACHE_FILENAME}")


if __name__ == "__main__":
    generate_docs()
