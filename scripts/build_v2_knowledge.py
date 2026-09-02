#!/usr/bin/env python3
"""Build the deterministic, offline Glyphs MCP v2 Knowledge corpus."""

from __future__ import annotations

import ast
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / "src/glyphs-mcp-v2/glyphs_mcp_v2/knowledge_data/index.json"
HANDBOOK = REPO / "Documentations/Markdown"
SDK = REPO / "GlyphsSDK"
GLYPHS_API = SDK / "ObjectWrapper/GlyphsApp"
SCHEMAS = SDK / "GlyphsFileFormat/Schemas"
GLYPHS_SDK_REVISION = "0f5422db727b78cb42abfb386f33ae0b382b0c4d"
CORPUS_VERSION = "2026.09.02"
VERIFIED_AT = "2026-09-02"


def _sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _title(text: str, fallback: str) -> str:
    match = re.search(r"^#{1,3}\s+(.+?)\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def _topics(value: str) -> list[str]:
    lowered = value.lower()
    candidates = {
        "spacing": ("spacing", "sidebearing", "metrics key", "width"),
        "kerning": ("kerning", "kern"),
        "outlines": ("path", "node", "outline", "curve"),
        "anchors": ("anchor",),
        "interpolation": ("interpol", "master", "brace layer", "bracket layer"),
        "variable-fonts": ("variable font", "axis", "avar"),
        "color-fonts": ("color font", "colr", "cpal", "svg"),
        "unicode": ("unicode", "codepoint", "glyph name"),
        "opentype": ("opentype", "feature", "gsub", "gpos"),
        "export": ("export", "instance", "fontmake"),
        "glyphs-python": ("python", "glyphsapp", "script"),
        "plugin-development": ("plugin", "reporter", "filter", "palette"),
        "file-format": ("file format", "schema", ".glyphs", "glyphspackage"),
        "vertical-metrics": ("vertical", "top bearing", "bottom bearing"),
    }
    result = [topic for topic, needles in candidates.items() if any(needle in lowered for needle in needles)]
    return result or ["glyphs"]


def _entry(
    *,
    identity: str,
    title: str,
    body: str,
    source_url: str,
    source_path: str,
    authority: str,
    topics: Iterable[str],
    glyphs_versions: Iterable[str] = ("3.5", "4"),
    keywords: Iterable[str] = (),
    examples: Iterable[str] = (),
    compatibility_notes: str = "",
) -> dict[str, Any]:
    normalized = body.strip()
    source_revision = (
        GLYPHS_SDK_REVISION
        if source_path.startswith("GlyphsSDK/")
        else CORPUS_VERSION
    )
    return {
        "id": identity,
        "title": title.strip(),
        "summary": re.sub(r"\s+", " ", normalized)[:280],
        "body": normalized,
        "topics": sorted(set(str(value) for value in topics)),
        "keywords": sorted(set(str(value).lower() for value in keywords)),
        "glyphsVersions": sorted(set(str(value) for value in glyphs_versions)),
        "authority": authority,
        "sourceUrl": source_url,
        "sourcePath": source_path,
        "sourceRevision": source_revision,
        "verifiedAt": VERIFIED_AT,
        "contentFingerprint": _sha(normalized),
        "citations": [
            {
                "url": source_url,
                "path": source_path,
                "revision": source_revision,
                "verifiedAt": VERIFIED_AT,
            }
        ],
        "examples": [str(value).strip() for value in examples if str(value).strip()],
        "compatibilityNotes": str(compatibility_notes or ""),
    }


def handbook_entries() -> list[dict[str, Any]]:
    result = []
    for path in sorted(HANDBOOK.glob("*.md")):
        body = path.read_text(encoding="utf-8")
        fallback = path.stem.split("_", 1)[-1].replace("_", " ").replace("-", " ").title()
        title = _title(body, fallback)
        result.append(
            _entry(
                identity="handbook." + _slug(path.stem),
                title=title,
                body=body,
                source_url="https://handbook.glyphsapp.com/",
                source_path=str(path.relative_to(REPO)),
                authority="authoritative",
                topics=_topics(title + "\n" + body),
                keywords=re.findall(r"[A-Za-z][A-Za-z0-9_.-]{2,}", title),
            )
        )
    return result


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    arguments = [argument.arg for argument in node.args.posonlyargs + node.args.args]
    if node.args.vararg:
        arguments.append("*" + node.args.vararg.arg)
    arguments.extend(argument.arg for argument in node.args.kwonlyargs)
    if node.args.kwarg:
        arguments.append("**" + node.args.kwarg.arg)
    return "{}({})".format(node.name, ", ".join(arguments))


def api_entries() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted(GLYPHS_API.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        module_name = ".".join(path.relative_to(SDK / "ObjectWrapper").with_suffix("").parts)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = _signature(node)
                doc = ast.get_docstring(node) or ""
                if not doc:
                    continue
                result.append(
                    _entry(
                        identity="api." + _slug(module_name + "." + node.name),
                        title=module_name + "." + name,
                        body=name + "\n\n" + doc,
                        source_url="https://docu.glyphsapp.com/",
                        source_path=str(path.relative_to(REPO)) + ":" + str(node.lineno),
                        authority="authoritative",
                        topics=["glyphs-python"],
                        keywords=[module_name, node.name, "python", "api"],
                    )
                )
            elif isinstance(node, ast.ClassDef):
                class_doc = ast.get_docstring(node) or ""
                if class_doc:
                    result.append(
                        _entry(
                            identity="api." + _slug(module_name + "." + node.name),
                            title=module_name + "." + node.name,
                            body=class_doc,
                            source_url="https://docu.glyphsapp.com/",
                            source_path=str(path.relative_to(REPO)) + ":" + str(node.lineno),
                            authority="authoritative",
                            topics=["glyphs-python", "plugin-development"] if "Plugin" in node.name else ["glyphs-python"],
                            keywords=[module_name, node.name, "python", "api"],
                        )
                    )
                for child in node.body:
                    if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    doc = ast.get_docstring(child) or ""
                    if not doc:
                        continue
                    name = _signature(child)
                    qualified = module_name + "." + node.name + "." + child.name
                    result.append(
                        _entry(
                            identity="api." + _slug(qualified),
                            title=module_name + "." + node.name + "." + name,
                            body=name + "\n\n" + doc,
                            source_url="https://docu.glyphsapp.com/",
                            source_path=str(path.relative_to(REPO)) + ":" + str(child.lineno),
                            authority="authoritative",
                            topics=["glyphs-python", "plugin-development"] if "Plugin" in node.name else ["glyphs-python"],
                            keywords=[module_name, node.name, child.name, "python", "api"],
                        )
                    )
    return result


def schema_entries() -> list[dict[str, Any]]:
    result = []
    for path in sorted(SCHEMAS.glob("*-4.schema.json")):
        body = path.read_text(encoding="utf-8")
        result.append(
            _entry(
                identity="file-format." + _slug(path.stem),
                title="Glyphs File Format v4: " + path.stem,
                body=body,
                source_url="https://github.com/schriftgestalt/GlyphsSDK/tree/Glyphs4/GlyphsFileFormat/Schemas",
                source_path=str(path.relative_to(REPO)),
                authority="authoritative",
                topics=["file-format", "glyphs-python"],
                glyphs_versions=["4"],
                keywords=["schema", "glyphs", "file format", path.stem],
            )
        )
    return result


def curated_entries() -> list[dict[str, Any]]:
    values = [
        (
            "practice.negative-sidebearings",
            "Negative sidebearings are evidence, not automatic errors",
            """Sidebearings are signed metrics, so negative values are legal. They commonly occur in italic overhangs, swashes, combining marks, and shapes such as J, j, f, or Q. Review the outline, writing direction, neighboring proofs, advance width, and design intent before changing one. Large unexpected negatives on ordinary upright base glyphs deserve inspection, but neither glyph name nor a fixed threshold proves an error. Useful proofs include HHHOHH, HOHOHO, AVAYAW, JHJOJ, nnnon, nonono, repeated figures, and punctuation beside capitals, lowercase, figures, and spaces.""",
            ["spacing", "outlines"],
            ["negative sidebearing", "overhang", "proof strings"],
            "practice",
        ),
        (
            "practice.spacing-physical-model",
            "Spacing metrics and physical writes",
            """For horizontal spacing, leading bearing equals the foreground bounds x-coordinate after translation; trailing bearing equals advance minus translated bounds maximum x. Changing one bearing is underdetermined until the agent explicitly chooses whether to preserve advance, preserve the opposite bearing, or translate geometry. Vertical spacing likewise separates vertical advance, vertical origin, top/bottom bearings, and y-translation. Always preview the explicit width/origin and geometry writes together and verify the resulting measured metrics.""",
            ["spacing", "vertical-metrics"],
            ["advance", "origin", "translation", "bearing"],
            "practice",
        ),
        (
            "practice.python-fallback",
            "Choosing declarative tools or Python",
            """Prefer generic reads, constraints, and immutable previews when canonical operations express the task. Use staged_document Python when a Glyphs API or multi-step transformation is not yet represented by generic operations; inspect its semantic preview and apply that stored patch without rerunning the code. Document-bound read_only Python also runs on a detached font and proves that the live canonical fingerprint and dirty state did not change. Reserve live_open_world for live-only UI, files, processes, networking, unsupported native objects, or other effects that cannot be made transactional. Never save the working font from Python; use save_document explicitly.""",
            ["glyphs-python", "plugin-development"],
            ["execute_python", "staged_document", "live_open_world"],
            "practice",
        ),
        (
            "practice.save-tolerant-fingerprints",
            "Separate live-document state from persisted file state",
            """A Glyphs MCP live-document fingerprint identifies the canonical state currently open in Glyphs. A source-file fingerprint identifies the bytes at the document's working path, and a destination-file fingerprint identifies bytes that a Save As or export could replace. A native Glyphs Save is always allowed and a save-only event does not stale an immutable change preview. During a verified transaction, saved input leaves the complete edit unsaved, saved output leaves no unsaved history entry, and an intermediate save rebases history to the residual saved-to-live semantic diff. Only save_document uses source and destination fingerprints as overwrite preconditions; never pass a live-document fingerprint in their place.""",
            ["file-format", "glyphs-python", "plugin-development"],
            ["save epoch", "document fingerprint", "source file fingerprint", "save_document"],
            "practice",
        ),
        (
            "practice.generic-mechanics",
            "Compose Glyphs work from generic mechanics",
            """Use EntitySelector predicates to resolve canonical evidence, typed ordering for numeric or textual comparisons, and Projection reducers for count, minimum, maximum, sum, average, any, or all. Express writes as exact discriminated set, translate, transform, insert, remove, move, duplicate, or materialize operations. Duplicate when the source is an existing entity; materialize an instance when Glyphs must authoritatively interpolate a new master. Supply the final newId in that operation. A master identity is an ownership root, so never attach it under a temporary ID and rename it after dependent layers exist. Require masterLayerCoverage on the baseline and proposed result, then compare exact source/target fields and geometry counts to prove content as well as existence. A preview stores exact identities, normalized operations, a base live-document fingerprint, semantic diff, and constraint evidence. Apply the stored patch without replanning. Typographic preservation choices and exceptions remain agent decisions in skills, not tool-side mutation policy.""",
            ["glyphs-python", "plugin-development", "spacing"],
            [
                "EntitySelector", "reducers", "preview_change", "apply_change",
                "materialize", "masterLayerCoverage", "master identity",
            ],
            "practice",
        ),
    ]
    entries = [
        _entry(
            identity=identity,
            title=title,
            body=body,
            source_url="https://github.com/thierryc/Glyphs-mcp/tree/main/skills",
            source_path="skills",
            authority=authority,
            topics=topics,
            keywords=keywords,
        )
        for identity, title, body, topics, keywords, authority in values
    ]
    alignment = _entry(
        identity="glyphs4.component-alignment-state",
        title="Configured and effective component alignment in Glyphs 4",
        body=(
            "Glyphs file-format v4 stores the component alignment mode as an integer: "
            "-1 disables automatic positioning, 0 requests contextual/default alignment, "
            "1 forces alignment, and 3 requests horizontal-only alignment. The "
            "GSComponent.automaticAlignment convenience getter reports whether the raw "
            "mode is non-negative; it does not prove that alignment is effective in the "
            "current layer. GSLayer.isAligned is the native layer-level observation that "
            "reports whether components are effectively auto-aligned. Under the normal "
            "eligibility rules, automatic alignment is enabled by default for "
            "component-only layers and disabled when paths are present; the font-wide "
            "Disable Automatic Alignment setting can also affect eligibility. Preserve "
            "the raw mode during ordinary geometry translation and use detached native "
            "read-back plus GSLayer.isAligned when effective behavior matters."
        ),
        source_url="https://docu.glyphsapp.com/",
        source_path="GlyphsSDK/ObjectWrapper/GlyphsApp/__init__.py:10889",
        authority="authoritative",
        topics=["glyphs-python", "file-format", "outlines", "spacing"],
        keywords=[
            "GSLayer.isAligned",
            "GSComponent.alignment",
            "automaticAlignment",
            "component alignment",
        ],
        glyphs_versions=["4"],
        examples=[
            "print({'effectiveLayerAlignment': bool(layer.isAligned), 'modes': [int(component.alignment) for component in layer.components]})"
        ],
        compatibility_notes=(
            "The pinned Glyphs 4 schema defines modes -1, 0, 1, and 3. "
            "Use GSLayer.isAligned for effective state rather than inferring it from mode 0."
        ),
    )
    alignment["citations"] = [
        {
            "url": "https://docu.glyphsapp.com/",
            "path": "GlyphsSDK/ObjectWrapper/GlyphsApp/__init__.py:10889",
            "revision": GLYPHS_SDK_REVISION,
            "verifiedAt": VERIFIED_AT,
        },
        {
            "url": "https://github.com/schriftgestalt/GlyphsSDK/tree/Glyphs4/GlyphsFileFormat/Schemas",
            "path": "GlyphsSDK/GlyphsFileFormat/Schemas/glyphs-4.schema.json:394",
            "revision": GLYPHS_SDK_REVISION,
            "verifiedAt": VERIFIED_AT,
        },
        {
            "url": "https://handbook.glyphsapp.com/components/",
            "path": "Documentations/Markdown/058_reusing-shapes_components.md",
            "revision": CORPUS_VERSION,
            "verifiedAt": VERIFIED_AT,
        },
    ]
    entries.append(alignment)
    metrics_keys = _entry(
        identity="glyphs4.metrics-key-resolution",
        title="Metrics keys resolve through native layer context in Glyphs 4",
        body=(
            "Glyph and layer metrics keys can reference another glyph by name or "
            "formula for left bearing, right bearing, or width. They are not "
            "synchronized automatically after the referenced glyph changes; "
            "GSLayer.syncMetrics() performs the native update. A normal glyph-level "
            "key applies across the font's masters, while a key prefixed with == is "
            "a local layer exception. Consequently each layer resolves the linked "
            "value in its own associated master or interpolation context, so the same "
            "key may produce different numeric values in different masters. Inspect "
            "inheritance.metrics keys, current values, and detached resolved values "
            "before asserting a result. If a retained key resolves to a value that "
            "differs from a proposed number, choose explicitly between preserving the "
            "key, changing or removing it, or changing the referenced glyph."
        ),
        source_url="https://handbook.glyphsapp.com/spacing/",
        source_path="Documentations/Markdown/055_spacing-and-kerning_spacing.md:62",
        authority="practice",
        topics=["glyphs-python", "spacing"],
        keywords=[
            "GSLayer.syncMetrics",
            "inheritance.metrics",
            "leftMetricsKey",
            "local metrics key",
            "metrics key",
            "same master",
        ],
        glyphs_versions=["4"],
        examples=[
            "print({'key': layer.leftMetricsKey, 'current': layer.LSB})\nlayer.syncMetrics()\nprint({'resolved': layer.LSB, 'masterId': layer.associatedMasterId})"
        ],
        compatibility_notes=(
            "Verified against the pinned Glyphs 4 ObjectWrapper and handbook. "
            "Resolve on a detached font because syncMetrics() changes the candidate layer."
        ),
    )
    metrics_keys["citations"] = [
        {
            "url": "https://handbook.glyphsapp.com/spacing/",
            "path": "Documentations/Markdown/055_spacing-and-kerning_spacing.md:62",
            "revision": CORPUS_VERSION,
            "verifiedAt": VERIFIED_AT,
        },
        {
            "url": "https://docu.glyphsapp.com/",
            "path": "GlyphsSDK/ObjectWrapper/GlyphsApp/__init__.py:9681",
            "revision": GLYPHS_SDK_REVISION,
            "verifiedAt": VERIFIED_AT,
        },
        {
            "url": "https://docu.glyphsapp.com/",
            "path": "GlyphsSDK/ObjectWrapper/GlyphsApp/__init__.py:11035",
            "revision": GLYPHS_SDK_REVISION,
            "verifiedAt": VERIFIED_AT,
        },
    ]
    entries.append(metrics_keys)
    entries.extend(
        (
            _entry(
                identity="coding.detached-layer-inspection",
                title="Inspect one exact layer in detached Python",
                body=(
                    "In staged_document execution, use the injected detached font "
                    "rather than the live Glyphs singleton. Resolve a glyph and exact "
                    "layer ID, then print bounded scalar evidence."
                ),
                source_url="https://docu.glyphsapp.com/",
                source_path="GlyphsSDK/ObjectWrapper/GlyphsApp/__init__.py",
                authority="practice",
                topics=["glyphs-python", "spacing", "outlines"],
                keywords=["GSFont", "GSGlyph", "GSLayer", "execute_python"],
                glyphs_versions=["3.5", "4"],
                examples=[
                    "glyph = font.glyphs['A']\nlayer = glyph.layers['MASTER_ID']\nprint({'width': layer.width, 'bounds': tuple(layer.bounds)})"
                ],
                compatibility_notes=(
                    "The detached font variable is supplied by Glyphs MCP staged_document. "
                    "Layer lookup by exact ID is preferred across Glyphs 3.5 and 4."
                ),
            ),
            _entry(
                identity="coding.detached-width-edit",
                title="Stage one exact layer-width edit",
                body=(
                    "Use staged_document only when the declarative set operation is "
                    "insufficient. Mutate the injected detached font; inspect the returned "
                    "semantic preview and apply it with apply_change."
                ),
                source_url="https://docu.glyphsapp.com/",
                source_path="GlyphsSDK/ObjectWrapper/GlyphsApp/__init__.py",
                authority="practice",
                topics=["glyphs-python", "spacing"],
                keywords=["GSLayer.width", "staged_document", "apply_change"],
                glyphs_versions=["3.5", "4"],
                examples=[
                    "layer = font.glyphs['A'].layers['MASTER_ID']\nlayer.width = 520"
                ],
                compatibility_notes=(
                    "GSLayer.width is available in the pinned Glyphs SDK. Generic "
                    "preview_change set operations remain preferred for this simple case."
                ),
            ),
            _entry(
                identity="coding.open-world-ui-boundary",
                title="Keep live UI work in open-world Python",
                body=(
                    "UI selectors and live application singletons are external effect "
                    "boundaries. Use live_open_world, require approval, and report that UI "
                    "effects are not transactionally replayable."
                ),
                source_url="https://docu.glyphsapp.com/",
                source_path="GlyphsSDK/ObjectWrapper/GlyphsApp/__init__.py",
                authority="practice",
                topics=["glyphs-python", "plugin-development"],
                keywords=["Glyphs.font", "newTab", "live_open_world"],
                glyphs_versions=["3.5", "4"],
                examples=["Glyphs.font.newTab('/A/B')"],
                compatibility_notes=(
                    "The live Glyphs singleton is intentionally unavailable to staged_document. "
                    "Prefer open_document_view when it covers the task."
                ),
            ),
        )
    )
    return entries


def verify_pinned_sources() -> None:
    for path in (HANDBOOK, GLYPHS_API, SCHEMAS):
        if not path.is_dir():
            raise SystemExit("pinned Knowledge source is missing: {}".format(path))
    try:
        revision = subprocess.run(
            ["git", "-C", str(SDK), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(SDK), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("could not verify the pinned GlyphsSDK revision") from exc
    if revision != GLYPHS_SDK_REVISION:
        raise SystemExit(
            "GlyphsSDK revision drift: expected {}, found {}".format(
                GLYPHS_SDK_REVISION, revision
            )
        )
    if dirty:
        raise SystemExit("GlyphsSDK contains unreviewed local changes")


def build_payload() -> str:
    verify_pinned_sources()
    entries = handbook_entries() + api_entries() + schema_entries() + curated_entries()
    entries.sort(key=lambda entry: entry["id"])
    ids = [entry["id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate Knowledge entry ID")
    manifest = {
        "schemaVersion": 1,
        "corpusVersion": CORPUS_VERSION,
        # A pinned corpus must reproduce byte-for-byte from the same sources.
        "generatedAt": VERIFIED_AT + "T00:00:00Z",
        "verifiedAt": VERIFIED_AT,
        "glyphsSdkRevision": GLYPHS_SDK_REVISION,
        "runtimeNetworkRequired": False,
        "entryCount": len(entries),
        "authorities": sorted({entry["authority"] for entry in entries}),
        "topics": sorted({topic for entry in entries for topic in entry["topics"]}),
    }
    payload = {"manifest": manifest, "entries": entries}
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the reviewed offline index differs from pinned sources",
    )
    arguments = parser.parse_args()
    rendered = build_payload()
    if arguments.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != rendered:
            raise SystemExit(
                "Knowledge index drift; run scripts/build_v2_knowledge.py and review the result"
            )
        print("Knowledge index is current: {}".format(OUTPUT.relative_to(REPO)))
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print("wrote Knowledge index to {}".format(OUTPUT.relative_to(REPO)))


if __name__ == "__main__":
    main()
