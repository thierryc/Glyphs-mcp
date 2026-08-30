#!/usr/bin/env python3
"""Capture native Glyphs 4 export behavior on a detached in-memory font.

This script is intentionally a host characterization harness, not an offline
fixture generator.  It must run inside Glyphs 4 with the approved disposable
font open and clean.  It never edits or saves that font.  A new, empty output
directory below ``/tmp`` and the full repository commit are explicit inputs.

Typical Macro Panel invocation (paths are examples, not defaults)::

    scope = {}
    exec(open("/path/to/scripts/capture_glyphs4_native_export_parity.py").read(), scope)
    scope["capture"](
        "/tmp/glyphs4-native-parity",
        "<40-hex-git-commit>",
        "/path/to/scripts/capture_glyphs4_native_export_parity.py",
    )

The result is still untrusted until
``scripts/validate_glyphs4_native_parity.py`` verifies the committed JSON and
the complete artifact inventory.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence


FIXTURE_ID = "glyphs4-native-export-parity-v1"
DISPOSABLE_PREFIX = "Glyphs MCP V2 Disposable"
REQUIRED_PROBES = (
    "rtl_class_orientation",
    "vertical_sign_yadvance",
    "contextual_boundary_semantics",
    "number_value_half_rounding",
)
HARNESS_REPOSITORY_PATH = "scripts/capture_glyphs4_native_export_parity.py"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class CaptureError(RuntimeError):
    pass


def _progress(message: str) -> None:
    """Emit a flushed host-side checkpoint for an otherwise opaque native run."""

    print("[glyphs4-native-parity] {}".format(message), flush=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(path: Path) -> str:
    """Hash one flat/package source without following links."""

    if path.is_symlink():
        raise CaptureError("the disposable source path is a symlink")
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(b"file\0")
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256_file(path)))
        return digest.hexdigest()
    if not path.is_dir():
        raise CaptureError("the disposable source is not a flat file or package")
    digest.update(b"directory\0")
    for child in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        relative = child.relative_to(path).as_posix()
        mode = child.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise CaptureError("the disposable source contains a link or special object: " + relative)
        digest.update(("d" if stat.S_ISDIR(mode) else "f").encode("ascii"))
        digest.update(b"\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if stat.S_ISREG(mode):
            digest.update(bytes.fromhex(_sha256_file(child)))
    return digest.hexdigest()


def _harness_sha256(harness_path: Path) -> str:
    path = Path(harness_path).resolve(strict=True)
    if path.name != Path(HARNESS_REPOSITORY_PATH).name:
        raise CaptureError("capture harness path is not identifiable")
    return _sha256_file(path)


def _native_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _native_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_native_value(item) for item in value]
    return str(value)


def _plain_attribute(value: Any, name: str, default: Any = None) -> Any:
    result = getattr(value, name, default)
    return result() if callable(result) else result


def _mapping_keys(value: Any) -> list[Any]:
    keys = getattr(value, "keys", None)
    if callable(keys):
        return list(keys())
    return []


def _mapping_get(value: Any, key: Any) -> Any:
    try:
        return value[key]
    except Exception:
        getter = getattr(value, "objectForKey_", None)
        return getter(key) if callable(getter) else None


def _native_mapping(value: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in _mapping_keys(value):
        item = _mapping_get(value, key)
        if _mapping_keys(item):
            result[str(key)] = _native_mapping(item)
        else:
            result[str(key)] = _native_value(item)
    return result


def _safe_output_root(value: str | os.PathLike[str]) -> tuple[Path, Path]:
    requested = Path(value)
    if not requested.is_absolute():
        raise CaptureError("output must be an absolute path")
    if requested.exists() or requested.is_symlink():
        raise CaptureError("output must not already exist")
    parent = requested.parent.resolve(strict=True)
    resolved = parent / requested.name
    temporary_root = Path("/private/tmp").resolve()
    try:
        resolved.relative_to(temporary_root)
    except ValueError as exc:
        raise CaptureError("output must be a new directory below /tmp") from exc
    if resolved == temporary_root or not requested.name.strip():
        raise CaptureError("output cannot be the temporary root")
    for ancestor in (parent, *parent.parents):
        if ancestor == temporary_root.parent:
            break
        if ancestor.is_symlink():
            raise CaptureError("output has a symlink ancestor")
    staging = parent / ("." + requested.name + ".capturing")
    if staging.exists() or staging.is_symlink():
        raise CaptureError("capture staging path already exists")
    return resolved, staging


def _rect_path(GSPath: Any, GSNode: Any, LINE: Any, x: int) -> Any:
    path = GSPath()
    for point in ((x, 0), (x + 300, 0), (x + 300, 500), (x, 500)):
        path.nodes.append(GSNode(point, LINE))
    path.closed = True
    return path


def _append_glyph(
    font: Any,
    master: Any,
    GSGlyph: Any,
    GSPath: Any,
    GSNode: Any,
    LINE: Any,
    name: str,
    unicode_value: str | None,
    *,
    direction: int | None = None,
    left_group: str | None = None,
    right_group: str | None = None,
    top_group: str | None = None,
    bottom_group: str | None = None,
) -> Any:
    glyph = GSGlyph(name, False)
    if unicode_value is not None:
        glyph.unicode = unicode_value
    if direction is not None:
        glyph.direction = direction
    if left_group is not None:
        glyph.leftKerningGroup = left_group
    if right_group is not None:
        glyph.rightKerningGroup = right_group
    if top_group is not None:
        glyph.topKerningGroup = top_group
    if bottom_group is not None:
        glyph.bottomKerningGroup = bottom_group
    font.glyphs.append(glyph)
    layer = glyph.layers[master.id]
    layer.width = 600
    layer.vertWidth = 1000
    # ``layer.paths`` is a read-only filtering proxy in Glyphs 4. Add paths
    # through the documented mutable ``layer.shapes`` collection instead.
    layer.shapes.append(_rect_path(GSPath, GSNode, LINE, len(font.glyphs) * 3))
    return glyph


def _fresh_probe_font_and_master(GSFont: Any, GSFontMaster: Any) -> tuple[Any, Any]:
    """Return a fresh font and its single master without duplicating host defaults."""

    font = GSFont()
    existing_masters = list(font.masters)
    if len(existing_masters) > 1:
        raise CaptureError("a fresh Glyphs font unexpectedly contains multiple masters")
    if existing_masters:
        master = existing_masters[0]
    else:
        master = GSFontMaster()
        font.masters.append(master)
    return font, master


def _build_probe_font() -> tuple[Any, dict[str, Any]]:
    _progress("constructing detached probe font")
    try:
        from GlyphsApp import (  # type: ignore[import-not-found]
            GSLTR,
            GSRTL,
            GSVertical,
            GSFeature,
            GSFont,
            GSFontMaster,
            GSGlyph,
            GSInstance,
            GSMetric,
            GSNode,
            GSPath,
            INSTANCETYPESINGLE,
            LINE,
        )
    except Exception as exc:
        raise CaptureError("capture must run inside Glyphs 4") from exc

    font, master = _fresh_probe_font_and_master(GSFont, GSFontMaster)
    font.familyName = "Glyphs MCP Native Export Parity"
    font.upm = 1000
    master.id = "11111111-1111-4111-8111-111111111111"
    master.name = "Regular"
    # Glyphs 4 resolves the default ascender/descender through font-owned
    # metric IDs. Attach the master before assigning those values so the
    # native setters never receive a nil metric key.
    master.ascender = 800
    master.descender = -200
    _progress("created detached master")

    glyph_specs = (
        (".notdef", None, GSLTR),
        ("A", "0041", GSLTR),
        ("B", "0042", GSLTR),
        ("C", "0043", GSLTR),
        ("D", "0044", GSLTR),
        ("L", "004C", GSLTR),
        ("l", "006C", GSLTR),
        ("O", "004F", GSLTR),
        ("quoteright", "2019", GSLTR),
    )
    glyphs: dict[str, Any] = {}
    for name, unicode_value, direction in glyph_specs:
        glyphs[name] = _append_glyph(
            font,
            master,
            GSGlyph,
            GSPath,
            GSNode,
            LINE,
            name,
            unicode_value,
            direction=direction,
        )
    _progress("created LTR probe glyphs")
    glyphs["alef-ar"] = _append_glyph(
        font,
        master,
        GSGlyph,
        GSPath,
        GSNode,
        LINE,
        "alef-ar",
        "0627",
        direction=GSRTL,
        right_group="rtl_first_right",
    )
    glyphs["beh-ar"] = _append_glyph(
        font,
        master,
        GSGlyph,
        GSPath,
        GSNode,
        LINE,
        "beh-ar",
        "0628",
        direction=GSRTL,
        left_group="rtl_second_left",
    )
    glyphs["verticalA"] = _append_glyph(
        font,
        master,
        GSGlyph,
        GSPath,
        GSNode,
        LINE,
        "verticalA",
        "E000",
        direction=GSVertical,
        bottom_group="vertical_first_bottom",
    )
    glyphs["verticalB"] = _append_glyph(
        font,
        master,
        GSGlyph,
        GSPath,
        GSNode,
        LINE,
        "verticalB",
        "E001",
        direction=GSVertical,
        top_group="vertical_second_top",
    )
    _progress("created directional probe glyphs")

    rtl_left = str(glyphs["alef-ar"].rightKerningKey)
    rtl_right = str(glyphs["beh-ar"].leftKerningKey)
    vertical_first = str(glyphs["verticalA"].bottomKerningKey)
    vertical_second = str(glyphs["verticalB"].topKerningKey)
    font.setKerningForPair(master.id, rtl_left, rtl_right, -73, GSRTL)
    font.setKerningForPair(master.id, vertical_first, vertical_second, -61, GSVertical)
    _progress("stored RTL and vertical kerning")

    context_setter = getattr(font, "setContextKerningForKey_fontMasterID_value_", None)
    if not callable(context_setter):
        context_setter = getattr(font, "setContextKerningForKey", None)
    if not callable(context_setter):
        raise CaptureError("Glyphs 4 exposes no contextual kerning setter")
    context_setter("L * quoteright A", master.id, -41)
    context_setter("L quoteright * A", master.id, 23)
    _progress("stored contextual kerning")

    number_inputs = (
        ("gmcpPositiveTwoHalf", 2.5, "A"),
        ("gmcpNegativeTwoHalf", -2.5, "B"),
        ("gmcpPositiveHalf", 0.5, "C"),
        ("gmcpNegativeHalf", -0.5, "D"),
    )
    feature_lines: list[str] = []
    for number_name, value, glyph_name in number_inputs:
        number = GSMetric()
        number.name = number_name
        font.numbers.append(number)
        _progress("created Number Value {}".format(number_name))
        master.numbers[number.id] = value
        _progress("stored Number Value {}".format(number_name))
        feature_lines.append("pos {} <${} 0 0 0>;".format(glyph_name, number_name))
    number_feature = GSFeature("cpsp", "\n".join(feature_lines))
    number_feature.automatic = False
    font.features.append(number_feature)
    kern_feature = GSFeature("kern", "# Automatic Code")
    kern_feature.automatic = True
    font.features.append(kern_feature)

    instance = GSInstance.alloc().initWithType_(INSTANCETYPESINGLE)
    instance.name = "Regular"
    instance.active = True
    instance.font = font
    font.instances.append(instance)
    _progress("finished detached probe font")
    inputs = {
        "masterId": str(master.id),
        "rtl": {
            "direction": "rtl",
            "firstGlyph": "alef-ar",
            "secondGlyph": "beh-ar",
            "firstKey": rtl_left,
            "secondKey": rtl_right,
            "value": -73,
        },
        "vertical": {
            "direction": "vertical",
            "firstGlyph": "verticalA",
            "secondGlyph": "verticalB",
            "firstKey": vertical_first,
            "secondKey": vertical_second,
            "value": -61,
        },
        "context": {
            "sequence": ["L", "quoteright", "A"],
            "boundaries": [
                {"nativeKey": "L * quoteright A", "boundaryIndex": 1, "value": -41},
                {"nativeKey": "L quoteright * A", "boundaryIndex": 2, "value": 23},
            ],
        },
        "numbers": [
            {"name": name, "value": value, "glyph": glyph_name}
            for name, value, glyph_name in number_inputs
        ],
    }
    return font, inputs


def _resolve_native_otf(artifact_root: Path, last_exported_path: Any) -> Path:
    """Resolve the new in-root OTF without trusting a stale native pointer."""

    reported = Path(str(last_exported_path or ""))
    if reported.is_file():
        try:
            reported.resolve().relative_to(artifact_root.resolve())
        except ValueError:
            pass
        else:
            return reported
    otfs = sorted(artifact_root.glob("*.otf"))
    if len(otfs) != 1:
        raise CaptureError("native OTF export did not create exactly one font")
    return otfs[0]


def _export_native(font: Any, artifact_root: Path) -> tuple[Path, Path]:
    try:
        from GlyphsApp import OTF, UFO  # type: ignore[import-not-found]
    except Exception as exc:
        raise CaptureError("capture must run inside Glyphs 4") from exc
    ufo_root = artifact_root / "native-ufo"
    ufo_root.mkdir()
    font.export(
        format=UFO,
        fontPath=str(ufo_root),
        useProductionNames=False,
        decomposeSmartStuff=False,
    )
    ufo_candidates = sorted(ufo_root.rglob("*.ufo"))
    if len(ufo_candidates) != 1:
        raise CaptureError("native UFO export did not create exactly one source")
    instance = font.instances[0]
    result = instance.generate(
        format=OTF,
        fontPath=str(artifact_root),
        autoHint=False,
        removeOverlap=False,
        useSubroutines=False,
        useProductionNames=False,
    )
    if result not in (None, True):
        raise CaptureError("native OTF export failed: " + str(result))
    exported = _resolve_native_otf(artifact_root, instance.lastExportedFilePath)
    return ufo_candidates[0], exported


def _ufo_observation(ufo: Path) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    groups_path = ufo / "groups.plist"
    kerning_path = ufo / "kerning.plist"
    features_path = ufo / "features.fea"
    if not groups_path.is_file() or not kerning_path.is_file() or not features_path.is_file():
        raise CaptureError("native UFO lacks groups.plist, kerning.plist, or features.fea")
    groups = plistlib.loads(groups_path.read_bytes())
    kerning = plistlib.loads(kerning_path.read_bytes())
    flat_kerning: list[dict[str, Any]] = []
    for first, seconds in sorted(kerning.items(), key=lambda item: str(item[0])):
        for second, value in sorted(seconds.items(), key=lambda item: str(item[0])):
            flat_kerning.append(
                {"first": str(first), "second": str(second), "value": float(value)}
            )
    feature_code = features_path.read_text(encoding="utf-8")
    return (
        {
            str(name): [str(glyph) for glyph in members]
            for name, members in sorted(groups.items(), key=lambda item: str(item[0]))
        },
        flat_kerning,
        feature_code,
    )


def _feature_lookup_indexes(ttfont: Any, tag: str) -> list[int]:
    table = ttfont["GPOS"].table
    indexes: list[int] = []
    for record in table.FeatureList.FeatureRecord:
        if record.FeatureTag == tag:
            indexes.extend(int(value) for value in record.Feature.LookupListIndex)
    return sorted(set(indexes))


def _value_record(record: Any) -> dict[str, int]:
    return {
        name: int(getattr(record, name, 0) or 0)
        for name in ("XPlacement", "YPlacement", "XAdvance", "YAdvance")
    }


def _unwrap_lookup_subtables(lookup: Any) -> Iterable[tuple[int, Any]]:
    for subtable in lookup.SubTable:
        if int(lookup.LookupType) == 9:
            yield int(subtable.ExtensionLookupType), subtable.ExtSubTable
        else:
            yield int(lookup.LookupType), subtable


def _pair_position(ttfont: Any, tag: str, first: str, second: str) -> dict[str, Any]:
    table = ttfont["GPOS"].table
    matches: list[dict[str, Any]] = []
    for lookup_index in _feature_lookup_indexes(ttfont, tag):
        lookup = table.LookupList.Lookup[lookup_index]
        for lookup_type, subtable in _unwrap_lookup_subtables(lookup):
            if lookup_type != 2 or first not in subtable.Coverage.glyphs:
                continue
            value1 = value2 = None
            if int(subtable.Format) == 1:
                pair_set = subtable.PairSet[subtable.Coverage.glyphs.index(first)]
                for record in pair_set.PairValueRecord:
                    if record.SecondGlyph == second:
                        value1, value2 = record.Value1, record.Value2
                        break
            elif int(subtable.Format) == 2:
                class1 = int(subtable.ClassDef1.classDefs.get(first, 0))
                class2 = int(subtable.ClassDef2.classDefs.get(second, 0))
                class_record = subtable.Class1Record[class1].Class2Record[class2]
                value1, value2 = class_record.Value1, class_record.Value2
            if value1 is not None or value2 is not None:
                matches.append(
                    {
                        "lookupIndex": lookup_index,
                        "value1": _value_record(value1),
                        "value2": _value_record(value2),
                    }
                )
    if not matches:
        raise CaptureError("compiled {} contains no pair {} {}".format(tag, first, second))
    return {"feature": tag, "matches": matches}


def _single_positions(ttfont: Any, tag: str, glyph_names: Sequence[str]) -> list[dict[str, Any]]:
    table = ttfont["GPOS"].table
    result: list[dict[str, Any]] = []
    for lookup_index in _feature_lookup_indexes(ttfont, tag):
        lookup = table.LookupList.Lookup[lookup_index]
        for lookup_type, subtable in _unwrap_lookup_subtables(lookup):
            if lookup_type != 1:
                continue
            for glyph_name in glyph_names:
                if glyph_name not in subtable.Coverage.glyphs:
                    continue
                coverage_index = subtable.Coverage.glyphs.index(glyph_name)
                value = (
                    subtable.Value
                    if int(subtable.Format) == 1
                    else subtable.Value[coverage_index]
                )
                result.append(
                    {
                        "glyph": glyph_name,
                        "lookupIndex": lookup_index,
                        **_value_record(value),
                    }
                )
    if len({item["glyph"] for item in result}) != len(set(glyph_names)):
        raise CaptureError("compiled Number Value feature omits a probe glyph")
    return sorted(result, key=lambda item: (item["glyph"], item["lookupIndex"]))


def _gpos_summary(ttfont: Any) -> dict[str, Any]:
    table = ttfont["GPOS"].table
    return {
        "features": [
            {
                "tag": record.FeatureTag,
                "lookupIndexes": [int(value) for value in record.Feature.LookupListIndex],
            }
            for record in table.FeatureList.FeatureRecord
        ],
        "lookupTypes": [int(lookup.LookupType) for lookup in table.LookupList.Lookup],
    }


def _hb_shape(executable: Path, font_path: Path, text: str, *, feature: str, direction: str) -> Any:
    command = [
        str(executable),
        "--output-format=json",
        "--features={}={}".format(feature, 1),
        "--direction=" + direction,
        str(font_path),
        text,
    ]
    enabled = subprocess.run(command, check=True, capture_output=True, text=True)
    command[2] = "--features={}={}".format(feature, 0)
    disabled = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(enabled.stdout), json.loads(disabled.stdout)


def _harfbuzz_executable() -> Path:
    configured = os.environ.get("GLYPHS_MCP_HB_SHAPE")
    candidate = configured or shutil.which("hb-shape")
    if not candidate:
        raise CaptureError("hb-shape is required for contextual and vertical native proof")
    path = Path(candidate).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise CaptureError("hb-shape is not an executable regular file")
    return path


def _artifact_entries(artifact_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(artifact_root.rglob("*"), key=lambda item: item.relative_to(artifact_root).as_posix()):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise CaptureError("native artifact contains a link or special object")
        if stat.S_ISREG(mode):
            entries.append(
                {
                    "relativePath": path.relative_to(artifact_root).as_posix(),
                    "byteSize": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
    return entries


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def capture(
    output_root: str | os.PathLike[str],
    repository_commit: str,
    harness_path: str | os.PathLike[str] | None = None,
) -> Path:
    """Capture and return the generated fixture JSON path."""

    if not COMMIT_RE.fullmatch(str(repository_commit or "")):
        raise CaptureError("repository_commit must be a full lowercase 40-hex Git object ID")
    final_root, staging = _safe_output_root(output_root)
    try:
        from GlyphsApp import Glyphs  # type: ignore[import-not-found]
    except Exception as exc:
        raise CaptureError("capture must run inside Glyphs 4") from exc
    selected_harness = harness_path or os.environ.get("GLYPHS_MCP_NATIVE_PARITY_HARNESS")
    if not selected_harness:
        selected_harness = globals().get("__file__")
    if not selected_harness:
        raise CaptureError(
            "harness_path is required when capture.py is loaded with exec()"
        )
    selected_harness_path = Path(str(selected_harness)).resolve(strict=True)
    harness_sha256 = _harness_sha256(selected_harness_path)
    version = str(
        _plain_attribute(Glyphs, "versionString", "")
        or _plain_attribute(Glyphs, "versionNumber", "")
    )
    build = str(_plain_attribute(Glyphs, "buildNumber", ""))
    if version.split(".", 1)[0] != "4" or int(float(build)) < 4004:
        raise CaptureError("capture requires Glyphs 4 build 4004 or newer")
    working = _plain_attribute(Glyphs, "font")
    if working is None or not str(_plain_attribute(working, "familyName", "") or "").startswith(DISPOSABLE_PREFIX):
        raise CaptureError("open the approved Glyphs MCP V2 Disposable font before capture")
    document = _plain_attribute(working, "parent")
    if document is None or bool(_plain_attribute(document, "isDocumentEdited", False)):
        raise CaptureError("the disposable working document must be clean")
    source_value = _plain_attribute(working, "filepath") or _plain_attribute(working, "filePath")
    source_path = Path(str(source_value or "")).resolve(strict=True)
    source_before = _tree_sha256(source_path)
    working_identity = id(working)
    working_path_before = str(source_path)

    staging.mkdir(mode=0o700)
    try:
        artifact_root = staging / "glyphs4-native-export-parity-artifacts"
        artifact_root.mkdir()
        probe_font, inputs = _build_probe_font()
        if _plain_attribute(probe_font, "parent") is not None:
            raise CaptureError("probe font unexpectedly belongs to a live document")
        _progress("starting native UFO and OTF export")
        ufo, otf = _export_native(probe_font, artifact_root)
        _progress("finished native UFO and OTF export")
        ufo_groups, ufo_kerning, exported_feature_source = _ufo_observation(ufo)

        try:
            from fontTools.ttLib import TTFont
        except Exception as exc:
            raise CaptureError("the Glyphs host requires fontTools for native evidence") from exc
        ttfont = TTFont(str(otf), lazy=False)
        if "GPOS" not in ttfont:
            raise CaptureError("native export contains no GPOS table")
        rtl_gpos = _pair_position(ttfont, "kern", "alef-ar", "beh-ar")
        vertical_gpos = _pair_position(ttfont, "vkrn", "verticalA", "verticalB")
        vertical_matches = vertical_gpos["matches"]
        vertical_x = sum(
            item[record]["XAdvance"]
            for item in vertical_matches
            for record in ("value1", "value2")
        )
        vertical_y = sum(
            item[record]["YAdvance"]
            for item in vertical_matches
            for record in ("value1", "value2")
        )
        number_adjustments = _single_positions(ttfont, "cpsp", ["A", "B", "C", "D"])
        summary = _gpos_summary(ttfont)
        ttfont.close()

        hb = _harfbuzz_executable()
        vertical_on, vertical_off = _hb_shape(
            hb,
            otf,
            "\ue000\ue001",
            feature="vkrn",
            direction="ttb",
        )
        positive_on, positive_off = _hb_shape(
            hb,
            otf,
            "L\u2019A",
            feature="kern",
            direction="ltr",
        )
        controls = []
        for text in ("L\u2019O", "l\u2019A", "\u2019A"):
            kern_on, kern_off = _hb_shape(
                hb,
                otf,
                text,
                feature="kern",
                direction="ltr",
            )
            controls.append({"text": text, "kernOn": kern_on, "kernOff": kern_off})

        native_context = getattr(probe_font, "kerningContext", None)
        native_context = native_context() if callable(native_context) else native_context
        observations = {
            "rtl_class_orientation": {
                "nativeInput": inputs["rtl"],
                "nativeStorage": _native_mapping(probe_font.kerningRTL),
                "ufoGroups": ufo_groups,
                "ufoKerning": ufo_kerning,
                "compiledGpos": rtl_gpos,
            },
            "vertical_sign_yadvance": {
                "nativeInput": inputs["vertical"],
                "compiledGpos": {
                    "feature": "vkrn",
                    "xAdvance": vertical_x,
                    "yAdvance": vertical_y,
                },
                "harfbuzz": {"vkrnOn": vertical_on, "vkrnOff": vertical_off},
            },
            "contextual_boundary_semantics": {
                "nativeInput": {
                    **inputs["context"],
                    "nativeStorage": _native_mapping(native_context),
                },
                "compiledGpos": summary,
                "harfbuzz": {
                    "positiveKernOn": positive_on,
                    "positiveKernOff": positive_off,
                    "negativeControls": controls,
                },
            },
            "number_value_half_rounding": {
                "nativeInput": inputs["numbers"],
                "exportedFeatureSource": exported_feature_source,
                "compiledAdjustments": number_adjustments,
            },
        }
        evidence_path = artifact_root / "native-observations.json"
        evidence_path.write_bytes(_json_bytes(observations))

        current_working = _plain_attribute(Glyphs, "font")
        current_document = _plain_attribute(current_working, "parent")
        current_source = _plain_attribute(current_working, "filepath") or _plain_attribute(current_working, "filePath")
        source_after = _tree_sha256(Path(str(current_source or "")).resolve(strict=True))
        working_changed = bool(
            id(current_working) != working_identity
            or str(Path(str(current_source or "")).resolve(strict=True)) != working_path_before
            or bool(_plain_attribute(current_document, "isDocumentEdited", False))
            or source_after != source_before
        )
        if working_changed:
            raise CaptureError("the working disposable document changed during capture")

        fixture = {
            "artifactRoot": "glyphs4-native-export-parity-artifacts",
            "artifacts": _artifact_entries(artifact_root),
            "blocker": None,
            "captureHarness": {
                "executionBoundary": "glyphs4_disposable_detached_export",
                "path": HARNESS_REPOSITORY_PATH,
                "sha256": harness_sha256,
            },
            "captureStatus": "captured",
            "fixtureId": FIXTURE_ID,
            "probes": [
                {
                    "id": probe_id,
                    "objective": objective,
                    "observation": observations[probe_id],
                    "requiredEvidence": required,
                    "status": "captured",
                }
                for probe_id, objective, required in (
                    (
                        "rtl_class_orientation",
                        "Characterize Glyphs native RTL group orientation through UFO and compiled GPOS output.",
                        ["native directional storage", "UFO groups and kerning", "compiled kern GPOS"],
                    ),
                    (
                        "vertical_sign_yadvance",
                        "Characterize native vertical kerning sign and YAdvance shaping behavior.",
                        ["compiled vkrn value records", "HarfBuzz ttb vkrn on/off"],
                    ),
                    (
                        "contextual_boundary_semantics",
                        "Characterize both native context-key boundaries and their additive shaping scope.",
                        ["native context storage", "compiled contextual GPOS", "positive and negative shaping controls"],
                    ),
                    (
                        "number_value_half_rounding",
                        "Characterize positive and negative half-unit Number Value rounding after native export.",
                        ["native UFO feature source", "compiled GPOS adjustments for four half ties"],
                    ),
                )
            ],
            "provenance": {
                "capturedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "harnessSha256": harness_sha256,
                "host": {"application": "Glyphs", "build": build, "version": version},
                "pythonVersion": sys.version.split()[0],
                "repositoryCommit": repository_commit,
                "sourceBoundary": "detached_in_memory_probe",
                "workingDocument": {
                    "changed": False,
                    "disposable": True,
                    "familyName": str(_plain_attribute(working, "familyName", "")),
                    "saved": False,
                    "sourceTreeSha256After": source_after,
                    "sourceTreeSha256Before": source_before,
                },
            },
            "requiredHost": {"application": "Glyphs", "applicationMajor": 4, "minimumBuild": 4004},
            "schemaVersion": 1,
            "surface": "glyphs-mcp-v2",
        }
        fixture_path = staging / "glyphs4-native-export-parity.json"
        fixture_path.write_bytes(_json_bytes(fixture))
        staging.replace(final_root)
    except Exception:
        if staging.exists() and not staging.is_symlink():
            shutil.rmtree(staging)
        raise
    print("Captured native Glyphs 4 parity evidence at {}".format(final_root))
    return final_root / "glyphs4-native-export-parity.json"


if __name__ == "__main__":
    output = os.environ.get("GLYPHS_MCP_NATIVE_PARITY_OUTPUT")
    commit = os.environ.get("GLYPHS_MCP_NATIVE_PARITY_REPOSITORY_COMMIT")
    if not output or not commit:
        raise SystemExit(
            "Set GLYPHS_MCP_NATIVE_PARITY_OUTPUT and "
            "GLYPHS_MCP_NATIVE_PARITY_REPOSITORY_COMMIT, or call capture() "
            "from the Glyphs Macro Panel."
        )
    capture(output, commit)
