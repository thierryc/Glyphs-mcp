"""Closed native instance generation and independent binary verification."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any, Mapping

from glyphs_mcp_protocol.compile_export import (
    MAX_ARTIFACT_FILE_BYTES,
    MAX_ARTIFACT_FILES,
    MAX_ARTIFACT_JOB_BYTES,
    validate_artifact_manifest,
)

from .worker import WorkerError


COMMON_TABLES = {"head", "hhea", "maxp", "hmtx", "cmap", "name", "post", "OS/2"}


def _value(owner: Any, name: str, default: Any = None) -> Any:
    try:
        result = getattr(owner, name)
        return result() if callable(result) else result
    except Exception:
        return default


def _instance_id(instance: Any) -> str:
    result = _value(instance, "id", None)
    return str(result or "")


def _instance_type(instance: Any) -> str:
    result = _value(instance, "type", None)
    if result in (1, "variable", "variableTT", "variableCFF"):
        return "variable"
    if result in (0, "single", "static"):
        return "static"
    raise WorkerError("Glyphs did not expose a supported instance type")


def _instance(font: Any, identity: str) -> Any:
    for candidate in list(_value(font, "instances", []) or []):
        if _instance_id(candidate) == identity:
            exports = _value(candidate, "exports", _value(candidate, "active", None))
            if exports not in (True, 1):
                raise WorkerError("the exact Glyphs instance is not enabled for export")
            return candidate
    raise WorkerError(f"instance {identity!r} is unavailable in the saved source")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def verify_font(path: Path, *, requested_format: str, container: str, variable: bool) -> dict[str, Any]:
    try:
        from fontTools.ttLib import TTFont
        font = TTFont(str(path), lazy=False, recalcBBoxes=False, recalcTimestamp=False)
    except Exception as exc:
        raise WorkerError(f"fontTools could not parse {path.name}: {exc}") from exc
    try:
        tables = set(font.keys())
        missing = sorted(COMMON_TABLES - tables)
        if missing:
            raise WorkerError(f"{path.name} is missing required OpenType tables: {', '.join(missing)}")
        if requested_format == "ttf":
            outline_required = {"glyf", "loca"}
        else:
            outline_required = {"CFF2"} if variable else {"CFF "}
        missing_outline = sorted(outline_required - tables)
        if missing_outline:
            raise WorkerError(f"{path.name} does not contain the requested {requested_format} outlines")
        if variable and "fvar" not in tables:
            raise WorkerError(f"{path.name} is missing the fvar table required for a variable export")
        observed_container = font.flavor or "plain"
        if observed_container != container:
            raise WorkerError(
                f"{path.name} container mismatch: requested {container}, observed {observed_container}"
            )
        return {
            "format": requested_format,
            "container": observed_container,
            "variable": variable,
            "glyphCount": len(font.getGlyphOrder()),
            "tables": sorted(tables),
        }
    finally:
        font.close()


def _shape(path: Path, case: Mapping[str, Any]) -> dict[str, Any]:
    try:
        import uharfbuzz as hb
    except ImportError as exc:
        raise WorkerError("HarfBuzz shaping verification is unavailable") from exc
    data = path.read_bytes()
    if data[:4] in (b"wOFF", b"wOF2"):
        from fontTools.ttLib import TTFont
        source = TTFont(io.BytesIO(data), lazy=False)
        try:
            source.flavor = None
            decoded = io.BytesIO()
            source.save(decoded)
            data = decoded.getvalue()
        finally:
            source.close()
    face = hb.Face(data)
    font = hb.Font(face)
    hb.ot_font_set_funcs(font)
    variations = case.get("variations") or {}
    if variations:
        font.set_variations(dict(variations))

    def run(text: str, enabled: bool):
        buffer = hb.Buffer()
        buffer.add_str(text)
        if case.get("direction"):
            buffer.direction = case["direction"]
        if case.get("script"):
            buffer.script = case["script"]
        if case.get("language"):
            buffer.language = case["language"]
        if not all((case.get("direction"), case.get("script"), case.get("language"))):
            buffer.guess_segment_properties()
        hb.shape(font, buffer, {case["feature"]: case["value"] if enabled else 0})
        return {
            "glyphs": [[item.codepoint, item.cluster] for item in buffer.glyph_infos],
            "positions": [[item.x_advance, item.y_advance, item.x_offset, item.y_offset]
                          for item in buffer.glyph_positions],
        }

    off = run(case["text"], False)
    on = run(case["text"], True)
    changed = off != on
    expected = case["expect"] == "different"
    if changed != expected:
        raise WorkerError(
            f"shaping case {case['feature']} expected {case['expect']} output"
        )
    result = {"feature": case["feature"], "expect": case["expect"], "passed": True,
              "off": off, "on": on}
    if case.get("controlText"):
        control_off = run(case["controlText"], False)
        control_on = run(case["controlText"], True)
        if control_off != control_on:
            raise WorkerError(f"shaping control changed for feature {case['feature']}")
        result["controlPassed"] = True
    return result


def _native_constants() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        from GlyphsApp import CFF, PLAIN, TT, WOFF, WOFF2  # type: ignore[import-not-found]
        return {"otf": CFF, "ttf": TT}, {"plain": PLAIN, "woff": WOFF, "woff2": WOFF2}
    except Exception:
        return {"otf": "CFF", "ttf": "TT"}, {"plain": "plain", "woff": "woff", "woff2": "woff2"}


def prepare(font: Any, request: Mapping[str, Any], job_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    options = request["options"]
    instance = _instance(font, options["instanceId"])
    instance_type = _instance_type(instance)
    variable = instance_type == "variable"
    generation = dict(options["generation"])
    if variable:
        if generation["removeOverlap"] is True:
            raise WorkerError("removeOverlap=true is unavailable for variable exports")
        generation["removeOverlap"] = False
    elif generation["removeOverlap"] is None:
        generation["removeOverlap"] = True

    staging = job_root / "artifacts"
    if staging.exists():
        raise WorkerError("artifact staging directory already exists")
    staging.mkdir(mode=0o700)
    formats, containers = _native_constants()
    method = getattr(instance, "generate", None)
    if not callable(method):
        raise WorkerError("Glyphs does not expose GSInstance.generate()")
    result = method(
        format=formats[options["format"]],
        fontPath=str(staging),
        autoHint=generation["autoHint"],
        removeOverlap=generation["removeOverlap"],
        useSubroutines=generation["useSubroutines"],
        useProductionNames=generation["useProductionNames"],
        containers=[containers[item] for item in options["containers"]],
        decomposeSmartStuff=generation["decomposeSmartComponents"],
    )
    if result not in (None, True):
        raise WorkerError(f"Glyphs export failed: {result}")

    files = []
    for candidate in sorted(staging.rglob("*")):
        if candidate.is_symlink():
            raise WorkerError("Glyphs export produced a symbolic link")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise WorkerError("Glyphs export produced a special file")
        files.append(candidate)
    if not 1 <= len(files) <= MAX_ARTIFACT_FILES:
        raise WorkerError("Glyphs export must produce 1-3 regular files")

    evidence, manifest_files, observed_containers, total = [], [], [], 0
    for candidate in files:
        size = candidate.stat().st_size
        if size > MAX_ARTIFACT_FILE_BYTES:
            raise WorkerError("exported file exceeds 512 MiB")
        total += size
        if total > MAX_ARTIFACT_JOB_BYTES:
            raise WorkerError("exported files exceed 1 GiB")
        # TTFont reports the actual sfnt flavor; do not trust file extensions.
        from fontTools.ttLib import TTFont
        parsed = TTFont(str(candidate), lazy=True)
        try:
            container = parsed.flavor or "plain"
        finally:
            parsed.close()
        observed_containers.append(container)
        verification = verify_font(
            candidate, requested_format=options["format"], container=container, variable=variable
        )
        shaping = [_shape(candidate, case) for case in options["verification"]["shapingCases"]]
        evidence.append({"path": candidate.relative_to(staging).as_posix(),
                         "tables": verification, "shapingCases": shaping})
        media = {("otf", "plain"): "font/otf", ("ttf", "plain"): "font/ttf",
                 ("otf", "woff"): "font/woff", ("ttf", "woff"): "font/woff",
                 ("otf", "woff2"): "font/woff2", ("ttf", "woff2"): "font/woff2"}[(options["format"], container)]
        manifest_files.append({
            "path": candidate.relative_to(staging).as_posix(),
            "size": size,
            "sha256": _sha256(candidate),
            "format": options["format"],
            "container": container,
            "mediaType": media,
        })
    if sorted(observed_containers) != sorted(options["containers"]):
        raise WorkerError("Glyphs export did not produce exactly the requested containers")
    manifest = validate_artifact_manifest({"files": manifest_files, "totalBytes": total})
    report = {
        "claim": "Staged and structurally verified font export",
        "success": True,
        "instanceId": options["instanceId"],
        "instanceName": str(_value(instance, "name", "") or ""),
        "instanceType": instance_type,
        "format": options["format"],
        "containers": list(options["containers"]),
        "generation": generation,
        "verification": {"tables": True, "files": evidence,
                         "shapingCases": list(options["verification"]["shapingCases"])},
        "warnings": [],
    }
    return manifest, report
