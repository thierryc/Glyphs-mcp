#!/usr/bin/env python3
"""Generate the searchable Glyphs MCP documentation bundle.

The generated bundle combines the official Glyphs Python ObjectWrapper and
plug-in APIs, scripting and plug-in guides, pinned Python templates, and the
Glyphs file-format specifications and schemas.
"""

from __future__ import annotations

import hashlib
import argparse
import ast
import json
import re
import shutil
import textwrap
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote


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


def _lean_api_sections(original: str):
    """Keep documented owners in source order; standalone functions have none.

    Wrapper methods may themselves be module functions. Prefer explicit native
    assignments in the code preceding their documentation over that ambiguity.
    """
    tree = ast.parse(original)
    functions = {n.name: n.lineno for n in tree.body if isinstance(n, ast.FunctionDef)}
    bindings = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                    bindings.append((node.lineno, target.value.id, target.attr))
    owner, previous_line = None, 0
    for number, match in enumerate(re.finditer(r"'''(.*?)'''", original, re.DOTALL), 1):
        section = match.group(1).strip()
        line = original.count("\n", 0, match.start()) + 1
        symbol = None
        first_member = True
        for directive in re.finditer(r"^\s*\.\. (class|attribute|method|function)::\s+([\w_]+)", section, re.M):
            kind, name = directive.groups()
            if kind == "class":
                owner = name
            elif first_member:
                explicit = [o for ln, o, member in bindings if previous_line < ln < line and member == name]
                if previous_line < functions.get(name, 0) < line:
                    symbol = explicit[-1] + "." + name if explicit else name
                    if not explicit:
                        owner = None
                elif owner:
                    symbol = owner + "." + name
                elif explicit:
                    symbol = explicit[-1] + "." + name
                first_member = False
        previous_line = original.count("\n", 0, match.end()) + 1
        yield number, section, symbol, line


def _verify_lean_sdk_sources(source_manifest):
    expected = source_manifest.get("sdkFileSha256")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("Pinned SDK source inventory is missing")
    actual = {p.relative_to(SDK_ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in SDK_ROOT.rglob("*") if p.is_file()
              and not any(part in (".git", "_build", "__pycache__") for part in p.parts)}
    changed = sorted(path for path in expected.keys() | actual.keys() if expected.get(path) != actual.get(path))
    if changed:
        raise ValueError("Pinned SDK sources changed: " + ", ".join(changed))


def generate_lean_documentation(output: Path) -> dict[str, Any]:
    """Build the offline development corpus without touching the v1 destination.

    Reuse the official-section extraction and normalization above. Original SDK
    text is also retained so section extraction is not an API coverage boundary.
    Provenance describes a pinned source snapshot, not native qualification.
    """
    output = Path(output)
    if output.resolve() == OUTPUT_ROOT.resolve():
        raise ValueError("The lean corpus must not overwrite v1 documentation")
    for source_root in (SDK_ROOT, HANDBOOK_ROOT):
        if not source_root.is_dir() or not any(p.is_file() for p in source_root.rglob("*")):
            raise FileNotFoundError("Required documentation source is missing: " + str(source_root))
    source_manifest = json.loads((REPO_ROOT / "skills/glyphs-mcp-development/assets/SOURCE.json").read_text())
    if source_manifest["revision"] != SDK_REVISION:
        raise ValueError("SDK and development templates have different pinned revisions")
    _verify_lean_sdk_sources(source_manifest)
    documents, sources = [], []
    docs = output / "docs"
    docs.mkdir(parents=True, exist_ok=True)

    def write(doc_id, destination, content, title, category, source, revision, url, **extra):
        data = content.encode("utf-8")
        path = docs / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        row = dict(id=doc_id, path=destination, title=title,
                   summary=(_summarize(content) or title)[:300],
                   searchTerms=sorted(set(re.findall(r"[a-z0-9_]+", content.lower()))),
                   checksum=hashlib.sha256(data).hexdigest(), sourceKind=category,
                   sourcePath=source, sourceRevision=revision, sourceUrl=url,
                   applicationTarget="4", nativeVerification="not-qualified-by-documentation",
                   **extra)
        row.setdefault("formatVersion", None)
        documents.append(row)

    original = OBJECT_WRAPPER_PATH.read_text(encoding="utf-8")
    for number, section, symbol, line in _lean_api_sections(original):
        title = _derive_title(section)
        if symbol:
            title = symbol + " — " + title
        write("api-section-" + str(number), "api/section_" + str(number) + ".rst",
              _normalize_generated_text(section), title, "glyphs-python-api",
              "GlyphsSDK/ObjectWrapper/GlyphsApp/__init__.py", SDK_REVISION,
              SDK_BLOB_BASE + "/ObjectWrapper/GlyphsApp/__init__.py",
              symbol=symbol, sourceChecksum=hashlib.sha256(OBJECT_WRAPPER_PATH.read_bytes()).hexdigest(),
              sourceLine=line)

    # The plugin wrapper uses normal Python docstrings. AST ownership gives
    # useful qualified names without importing GlyphsApp or inferring APIs.
    plugin_path = SDK_ROOT / "ObjectWrapper/GlyphsApp/plugins.py"
    plugin_text = plugin_path.read_text(encoding="utf-8")
    for cls in ast.parse(plugin_text).body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for member in [cls, *cls.body]:
            if not isinstance(member, (ast.ClassDef, ast.FunctionDef)):
                continue
            documentation = ast.get_docstring(member)
            if not documentation:
                continue
            symbol = cls.name if member is cls else cls.name + "." + member.name
            write("plugin-api:" + symbol, "plugin-api/" + symbol + ".txt",
                  documentation + "\n", symbol, "glyphs-plugin-api",
                  "GlyphsSDK/ObjectWrapper/GlyphsApp/plugins.py", SDK_REVISION,
                  SDK_BLOB_BASE + "/ObjectWrapper/GlyphsApp/plugins.py",
                  symbol=symbol, sourceLine=member.lineno,
                  sourceChecksum=hashlib.sha256(plugin_path.read_bytes()).hexdigest())

    # Keep the entire available source corpus, including guide illustrations
    # and sample bundle assets. Binary support files are not text search hits.
    support_files = []
    for source_root, prefix in ((SDK_ROOT, "sdk"), (HANDBOOK_ROOT, "handbook")):
        for path in sorted(source_root.rglob("*")):
            if not path.is_file() or any(p in path.parts for p in (".git", "_build", "__pycache__")):
                continue
            relative = path.relative_to(source_root).as_posix()
            data = path.read_bytes()
            source_path = ("GlyphsSDK/" if prefix == "sdk" else "Documentations/Markdown/") + relative
            digest = hashlib.sha256(data).hexdigest()
            sources.append(dict(path=source_path, sha256=digest))
            try:
                content = data.decode("utf-8")
                if "\0" in content:
                    raise UnicodeError()
            except UnicodeError:
                destination = prefix + "/" + relative
                asset = docs / destination
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_bytes(data)
                support_files.append(dict(path=destination, checksum=digest, sourcePath=source_path,
                    sourceRevision=SDK_REVISION if prefix == "sdk" else None,
                    sourceUrl=SDK_BLOB_BASE + "/" + quote(relative) if prefix == "sdk" else "https://handbook.glyphsapp.com/",
                    sourceKind="glyphs-sdk-support" if prefix == "sdk" else "glyphs-handbook-support",
                    indexed=False, reason="binary or non-UTF-8 support file; retained unchanged"))
                continue
            if prefix == "sdk":
                title = relative
                url = SDK_BLOB_BASE + "/" + quote(relative)
                revision = SDK_REVISION
                category = "glyphs-sdk-source"
            else:
                title = _derive_title(content) if content.startswith("..") else next(
                    (line.lstrip("# ").strip() for line in content.splitlines() if line.startswith("#")), relative)
                url = "https://handbook.glyphsapp.com/"
                revision = None
                category = "glyphs-handbook"
            format_match = re.search(r"(?:[Vv]|[-_])([234])(?:\.schema)?\.(?:md|json)$", relative)
            write(prefix + ":" + relative, prefix + "/" + relative, content, title,
                  category, source_path, revision, url, sourceChecksum=digest,
                  formatVersion=int(format_match.group(1)) if format_match and "GlyphsFileFormat" in source_path else None)

    documents.sort(key=lambda row: row["id"])
    payload = dict(schemaVersion=1, applicationTarget="4", sourceRevision=SDK_REVISION, documents=documents)
    index_bytes = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    (output / "index.json").write_bytes(index_bytes)
    manifest = dict(schemaVersion=1, applicationTarget="4", sourceRevision=SDK_REVISION,
                    indexSha256=hashlib.sha256(index_bytes).hexdigest(),
                    sourceInventory=sources, supportFiles=support_files,
                    documents={row["path"]: row["checksum"] for row in documents},
                    scope="All available SDK sources/references, support assets and vendored handbook; text indexed; excludes generated caches/builds.",
                    handbookProvenance="Vendored snapshot identified by per-file SHA-256; exact upstream revision unavailable.",
                    nativeVerification="Source documentation is not a native compatibility test.")
    (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    expected = set(manifest["documents"]) | {row["path"] for row in support_files}
    for stale in docs.rglob("*"):
        if stale.is_file() and stale.relative_to(docs).as_posix() not in expected:
            stale.unlink()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lean-output", type=Path, help="Build the standalone Glyphs 4 skill corpus at this path.")
    args = parser.parse_args()
    if args.lean_output:
        payload = generate_lean_documentation(args.lean_output)
        print(json.dumps({"documents": len(payload["documents"]), "sourceRevision": payload["sourceRevision"]}))
        return 0
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
