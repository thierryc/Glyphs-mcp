#!/usr/bin/env python3
"""Generate the searchable Glyphs MCP documentation bundle.

The generated bundle combines the official Glyphs Python ObjectWrapper
documentation with the pinned Glyphs file-format specifications and schemas.
Keeping the generator in this repository avoids requiring a custom GlyphsSDK
fork while still making the official references available to MCP clients.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import textwrap
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[3]
SDK_ROOT = REPO_ROOT / "GlyphsSDK"
SDK_REVISION = "0f5422db727b78cb42abfb386f33ae0b382b0c4d"
SDK_BLOB_BASE = "https://github.com/schriftgestalt/GlyphsSDK/blob/{}".format(SDK_REVISION)
OBJECT_WRAPPER_PATH = SDK_ROOT / "ObjectWrapper" / "GlyphsApp" / "__init__.py"
FILE_FORMAT_ROOT = SDK_ROOT / "GlyphsFileFormat"
OUTPUT_ROOT = (
    REPO_ROOT
    / "src"
    / "glyphs-mcp"
    / "Glyphs MCP.glyphsPlugin"
    / "Contents"
    / "Resources"
    / "MCP Documentation"
)
DOCS_ROOT = OUTPUT_ROOT / "docs"

FORMAT_DOCUMENTS = (
    {
        "id": "glyphs-file-format-v3",
        "source": "GlyphsFileFormatv3.md",
        "destination": "file-format/GlyphsFileFormatv3.md",
        "title": "Glyphs File Format, Version 3",
        "summary": "Official specification for version 3 .glyphs and .glyphspackage sources.",
        "sourceKind": "glyphs-file-format",
        "formatVersion": 3,
        "keywords": "file format version 3 glyphs glyphspackage source",
    },
    {
        "id": "glyphs-file-format-v4",
        "source": "GlyphsFileFormatv4.md",
        "destination": "file-format/GlyphsFileFormatv4.md",
        "title": "Glyphs File Format, Version 4",
        "summary": "Official specification for version 4 .glyphs and .glyphspackage sources.",
        "sourceKind": "glyphs-file-format",
        "formatVersion": 4,
        "keywords": (
            "file format version 4 glyphs glyphspackage shape group higher-order "
            "interpolation quartic gradients palettes contextual kerning"
        ),
    },
)

SCHEMA_DOCUMENTS = tuple(
    {
        "id": "glyphs-file-format-schema-{}-v{}".format(kind, version),
        "source": "Schemas/{}-{}.schema.json".format(kind, version),
        "destination": "file-format/schemas/{}-{}.schema.json".format(kind, version),
        "title": "Glyphs File Format {} Schema, Version {}".format(
            ".glyphs" if kind == "glyphs" else "fontinfo.plist",
            version,
        ),
        "summary": "Official JSON Schema for version {} {} sources.".format(
            version,
            ".glyphs" if kind == "glyphs" else ".glyphspackage fontinfo.plist",
        ),
        "sourceKind": "glyphs-file-format-schema",
        "formatVersion": version,
        "keywords": (
            "file format version {} schema {}{}".format(
                version,
                kind,
                (
                    " shape group higher-order interpolation quartic gradients "
                    "palettes contextual kerning"
                    if version == 4
                    else ""
                ),
            )
        ),
    }
    for version in (3, 4)
    for kind in ("glyphs", "fontinfo")
)

SKIP_BLOCK_DIRECTIVES = {
    "autosummary",
    "code-block",
    "figure",
    "image",
    "seealso",
}
DIRECTIVE_RE = re.compile(r"^\.\.\s+(?P<role>\w+)::\s*(?P<target>.+)$")
ROLE_LINE_RE = re.compile(r"^:(?P<role>\w+):`(?P<target>[^`]+)`$")
INLINE_ROLE_RE = re.compile(r":(?P<role>\w+):`(?P<target>[^`]+)`")
DOUBLE_BACKTICK_RE = re.compile(r"``([^`]+)``")
CONFLICT_MARKER_LINES = {"<<<<<<<", "=======", ">>>>>>>"}


def _extract_sections(path: Path) -> list[str]:
    content = path.read_text(encoding="utf-8")
    return [part.strip() for part in re.findall(r"'''(.*?)'''", content, re.DOTALL)]


def _normalize_generated_text(text: str) -> str:
    """Keep generated references reproducible and safe for Git patch checks."""

    lines = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line in CONFLICT_MARKER_LINES:
            # A seven-character reStructuredText heading underline looks like a
            # merge marker to `git diff --check`. Hyphens are equivalent RST.
            line = "-" * len(line)
        lines.append(line)
    return "\n".join(lines).strip() + "\n"


def _looks_like_heading(line: str, underline: str) -> bool:
    underline = underline.strip()
    return bool(
        line
        and underline
        and len(underline) >= len(line)
        and len(set(underline)) == 1
    )


def _clean_text(text: str) -> str:
    cleaned = INLINE_ROLE_RE.sub(lambda match: match.group("target"), text)
    cleaned = DOUBLE_BACKTICK_RE.sub(r"\1", cleaned)
    cleaned = cleaned.replace("`", "")
    return " ".join(cleaned.split())


def _derive_title(section: str) -> str:
    lines = textwrap.dedent(section).strip().splitlines()
    for index in range(len(lines) - 1):
        candidate = lines[index].strip()
        if candidate and _looks_like_heading(candidate, lines[index + 1]):
            return _clean_text(candidate)

    for raw in lines:
        stripped = raw.strip()
        match = DIRECTIVE_RE.match(stripped) or ROLE_LINE_RE.match(stripped)
        if match:
            target = _clean_text(match.group("target"))
            if target:
                return "{} ({})".format(target, match.group("role"))

    for raw in lines:
        candidate = _clean_text(raw.strip())
        if candidate:
            return candidate
    return "Untitled section"


def _iter_plaintext_lines(lines: Iterable[str]) -> Iterable[str]:
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
        if stripped.startswith(":") and ":" in stripped[1:]:
            continue
        if len(set(stripped)) == 1 and stripped[0] in "=-~`^'\"*+#_":
            continue
        yield stripped


def _summarize(section: str) -> str:
    lines = textwrap.dedent(section).splitlines()
    for index in range(len(lines) - 1):
        candidate = lines[index].strip()
        if candidate and _looks_like_heading(candidate, lines[index + 1]):
            lines = lines[index + 2 :]
            break

    paragraph_lines: list[str] = []
    for line in _iter_plaintext_lines(lines):
        if not line:
            if paragraph_lines:
                break
            continue
        paragraph_lines.append(_clean_text(line))

    paragraph = " ".join(paragraph_lines).strip()
    if not paragraph:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    return " ".join(sentences[:2]).strip() or paragraph


def _clean_generated_docs() -> None:
    DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    for path in DOCS_ROOT.glob("section_*.rst"):
        path.unlink()
    format_root = DOCS_ROOT / "file-format"
    if format_root.exists():
        shutil.rmtree(format_root)


def _write_object_wrapper_docs() -> list[dict[str, Any]]:
    sections = _extract_sections(OBJECT_WRAPPER_PATH)
    if not sections:
        raise RuntimeError("No ObjectWrapper documentation blocks found")

    documents: list[dict[str, Any]] = []
    source_url = "{}/ObjectWrapper/GlyphsApp/__init__.py".format(SDK_BLOB_BASE)
    for index, section in enumerate(sections, start=1):
        normalized_section = _normalize_generated_text(section)
        doc_id = "section_{}".format(index)
        relative_path = "{}.rst".format(doc_id)
        checksum = hashlib.sha256(normalized_section.encode("utf-8")).hexdigest()
        title = _derive_title(section)
        summary = _summarize(section) or title
        (DOCS_ROOT / relative_path).write_text(normalized_section, encoding="utf-8")
        documents.append(
            {
                "id": doc_id,
                "path": relative_path,
                "title": title,
                "summary": summary,
                "checksum": checksum,
                "sourceKind": "glyphs-python-api",
                "formatVersion": None,
                "sourceUrl": source_url,
            }
        )
    return documents


def _copy_reference(entry: dict[str, Any]) -> dict[str, Any]:
    source = FILE_FORMAT_ROOT / entry["source"]
    if not source.is_file():
        raise FileNotFoundError("Missing GlyphsSDK reference: {}".format(source))

    destination = DOCS_ROOT / entry["destination"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() in {".md", ".rst"}:
        destination.write_text(
            _normalize_generated_text(source.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
    else:
        shutil.copy2(source, destination)
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    source_url = "{}/GlyphsFileFormat/{}".format(SDK_BLOB_BASE, entry["source"])
    return {
        "id": entry["id"],
        "path": entry["destination"],
        "title": entry["title"],
        "summary": entry["summary"],
        "checksum": checksum,
        "sourceKind": entry["sourceKind"],
        "formatVersion": entry["formatVersion"],
        "sourceUrl": source_url,
        "keywords": entry.get("keywords", ""),
    }


def generate_documentation() -> dict[str, Any]:
    if not OBJECT_WRAPPER_PATH.is_file():
        raise FileNotFoundError(
            "GlyphsSDK is missing or not initialized: {}".format(OBJECT_WRAPPER_PATH)
        )

    _clean_generated_docs()
    documents = _write_object_wrapper_docs()
    documents.extend(
        _copy_reference(entry)
        for entry in FORMAT_DOCUMENTS + SCHEMA_DOCUMENTS
    )

    payload = {
        "version": 3,
        "sourceRevision": SDK_REVISION,
        "documents": documents,
        "titles": {document["id"]: document["title"] for document in documents},
    }
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "index.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    payload = generate_documentation()
    print(
        "Wrote {} documentation pages from GlyphsSDK {}".format(
            len(payload["documents"]),
            payload["sourceRevision"][:12],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
