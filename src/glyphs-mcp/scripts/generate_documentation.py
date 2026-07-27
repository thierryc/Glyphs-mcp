#!/usr/bin/env python3
"""Generate the searchable Glyphs MCP documentation bundle.

The generated bundle combines the official Glyphs Python ObjectWrapper and
plug-in APIs, scripting and plug-in guides, pinned Python templates, and the
Glyphs file-format specifications and schemas.
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
HANDBOOK_ROOT = REPO_ROOT / "Documentations" / "Markdown"
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

PLUGIN_TEMPLATE_SPECS = (
    (
        "general",
        "General Plugin",
        "____PluginName____.glyphsPlugin",
        "GeneralPlugin",
        "a general Glyphs Python plug-in",
        "menu start settings",
    ),
    (
        "reporter",
        "Reporter",
        "____PluginName____.glyphsReporter",
        "ReporterPlugin",
        "drawing foreground and background reports in Edit View",
        "foreground background drawing Edit View",
    ),
    (
        "filter",
        "Filter/without dialog",
        "____PluginName____.glyphsFilter",
        "FilterWithoutDialog",
        "a Glyphs filter plug-in without a dialog",
        "filter custom parameters export layer",
    ),
    (
        "palette",
        "Palette",
        "____PluginName____.glyphsPalette",
        "PalettePlugin",
        "palette callbacks, views, and Vanilla interfaces",
        "palette callback Vanilla dialog view",
    ),
    (
        "select-tool",
        "SelectTool",
        "____PluginName____.glyphsTool",
        "SelectTool",
        "custom selection tools, drawing, and context menus",
        "select tool context menu foreground background toolbar",
    ),
    (
        "file-format",
        "File Format",
        "dialog with vanilla/____PluginName____.glyphsFileFormat",
        "FileFormatPlugin",
        "custom Glyphs file-format import and export plug-ins",
        "file format import export Vanilla",
    ),
)

DEVELOPMENT_DOCUMENTS = (
    {
        "id": "glyphs-handbook-scripts",
        "sourceRoot": "handbook",
        "source": "117_extensions_scripts.md",
        "destination": "development/handbook-scripts.md",
        "title": "Creating Glyphs Scripts",
        "summary": "Official Glyphs Handbook guidance for creating and organizing Python scripts.",
        "sourceKind": "glyphs-handbook",
        "sourceUrl": "https://handbook.glyphsapp.com/scripts/",
        "keywords": "creating Glyphs scripts MenuTitle Python Scripts folder",
    },
    {
        "id": "glyphs-handbook-plugins",
        "sourceRoot": "handbook",
        "source": "118_extensions_plugins.md",
        "destination": "development/handbook-plugins.md",
        "title": "Creating Glyphs Plug-ins",
        "summary": "Official Glyphs Handbook overview of Python and Objective-C plug-in types and installation.",
        "sourceKind": "glyphs-handbook",
        "sourceUrl": "https://handbook.glyphsapp.com/plugins/",
        "keywords": "creating Glyphs plugins plug-ins reporter filter palette file format tool general",
    },
    {
        "id": "glyphs-python-plugin-api",
        "sourceRoot": "sdk",
        "source": "ObjectWrapper/GlyphsApp/plugins.py",
        "destination": "development/plugins.py",
        "title": "Glyphs Python Plug-in API",
        "summary": "Official Python wrapper implementation and lifecycle methods for Glyphs plug-in base classes.",
        "sourceKind": "glyphs-plugin-api",
        "keywords": "FileFormatPlugin FilterWithDialog FilterWithoutDialog GeneralPlugin PalettePlugin ReporterPlugin SelectTool",
    },
    {
        "id": "glyphs-python-plugin-template-overview",
        "sourceRoot": "sdk",
        "source": "Python Templates/README.md",
        "destination": "development/templates/README.md",
        "title": "Glyphs Python Plug-in Templates",
        "summary": "Official SDK instructions for metadata, placeholders, user interfaces, and Python plug-in packaging.",
        "sourceKind": "glyphs-plugin-template",
        "keywords": "Glyphs Python plug-in templates Info.plist principal class placeholders Xcode Vanilla",
    },
    {
        "id": "glyphs-python-plugin-info-plist",
        "sourceRoot": "sdk",
        "source": "Python Templates/General Plugin/____PluginName____.glyphsPlugin/Contents/Info.plist",
        "destination": "development/templates/Info.plist",
        "title": "Glyphs Python Plug-in Info.plist Template",
        "summary": "Official SDK bundle metadata template for Python plug-ins.",
        "sourceKind": "glyphs-plugin-template-source",
        "keywords": "Info.plist CFBundleIdentifier NSPrincipalClass PyMainFileNames plugin metadata",
    },
    {
        "id": "glyphs-sdk-license",
        "sourceRoot": "sdk",
        "source": "LICENSE",
        "destination": "development/GlyphsSDK-LICENSE.txt",
        "title": "GlyphsSDK Apache 2.0 License",
        "summary": "License and redistribution terms for the pinned GlyphsSDK templates and source.",
        "sourceKind": "glyphs-sdk-license",
        "keywords": "GlyphsSDK license Apache 2.0 attribution",
    },
) + tuple(
    document
    for slug, folder, bundle, class_name, purpose, keywords in PLUGIN_TEMPLATE_SPECS
    for document in (
        {
            "id": "glyphs-python-{}-guide".format(slug),
            "sourceRoot": "sdk",
            "source": "Python Templates/{}/README.md".format(folder),
            "destination": "development/templates/{}/README.md".format(slug),
            "title": "{} Template Guide".format(class_name),
            "summary": "Official SDK guide for {}.".format(purpose),
            "sourceKind": "glyphs-plugin-template",
            "keywords": "{} {}".format(class_name, keywords),
        },
        {
            "id": "glyphs-python-{}-source".format(slug),
            "sourceRoot": "sdk",
            "source": "Python Templates/{}/{}/Contents/Resources/plugin.py".format(
                folder, bundle
            ),
            "destination": "development/templates/{}/plugin.py".format(slug),
            "title": "{} Template Source".format(class_name),
            "summary": "Official SDK Python source template for {}.".format(purpose),
            "sourceKind": "glyphs-plugin-template-source",
            "keywords": "{} source plugin.py {}".format(class_name, keywords),
        },
    )
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
    development_root = DOCS_ROOT / "development"
    if development_root.exists():
        shutil.rmtree(development_root)


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
    source_root_name = entry.get("sourceRoot", "file-format")
    source_root = {
        "file-format": FILE_FORMAT_ROOT,
        "sdk": SDK_ROOT,
        "handbook": HANDBOOK_ROOT,
    }.get(source_root_name)
    if source_root is None:
        raise ValueError("Unknown documentation source root: {}".format(source_root_name))
    source = source_root / entry["source"]
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
    source_url = entry.get("sourceUrl")
    if not source_url:
        if source_root_name == "file-format":
            source_url = "{}/GlyphsFileFormat/{}".format(
                SDK_BLOB_BASE, entry["source"]
            )
        else:
            source_url = "{}/{}".format(
                SDK_BLOB_BASE, entry["source"].replace(" ", "%20")
            )
    return {
        "id": entry["id"],
        "path": entry["destination"],
        "title": entry["title"],
        "summary": entry["summary"],
        "checksum": checksum,
        "sourceKind": entry["sourceKind"],
        "formatVersion": entry.get("formatVersion"),
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
        for entry in FORMAT_DOCUMENTS + SCHEMA_DOCUMENTS + DEVELOPMENT_DOCUMENTS
    )

    payload = {
        "version": 4,
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
