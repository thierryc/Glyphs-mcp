"""Small read-only UFO adapter for the italic benchmark.

The benchmark's geometry helpers use the subset of the Glyphs object model
listed below.  Keeping the adapter here lets the same deterministic engine run
against pinned UFO sources without converting or modifying those sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from defcon import Font as DefconFont


@dataclass(frozen=True)
class _Position:
    x: float
    y: float


class _Node:
    def __init__(self, point: Any) -> None:
        self.position = _Position(float(point.x), float(point.y))
        self.type = str(point.segmentType or "offcurve")
        self.smooth = bool(point.smooth)


class _Path:
    def __init__(self, contour: Any) -> None:
        self.closed = not bool(contour.open)
        self.nodes = [_Node(point) for point in contour]


class _Anchor:
    def __init__(self, anchor: Any) -> None:
        self.name = str(anchor.name or "")
        self.position = _Position(float(anchor.x), float(anchor.y))


class _Component:
    def __init__(self, component: Any) -> None:
        self.componentName = str(component.baseGlyph)
        self.name = self.componentName
        self.transform = tuple(float(value) for value in component.transformation)


class _Layer:
    def __init__(self, glyph: Any) -> None:
        self.paths = [_Path(contour) for contour in glyph]
        self.anchors = [_Anchor(anchor) for anchor in glyph.anchors]
        self.components = [
            _Component(component) for component in glyph.components
        ]
        self.width = float(glyph.width or 0.0)


class _Glyph:
    def __init__(self, glyph: Any, master_id: str) -> None:
        self.name = str(glyph.name)
        self.unicodes = tuple(int(value) for value in glyph.unicodes)
        self.layers = {master_id: _Layer(glyph)}


class _GlyphProxy:
    def __init__(self, mapping: dict[str, _Glyph]) -> None:
        self._mapping = mapping

    def __getitem__(self, key: str) -> _Glyph | None:
        return self._mapping.get(str(key))

    def __iter__(self):
        return iter(self._mapping.values())


class UFOMaster:
    def __init__(
        self,
        source: DefconFont,
        *,
        master_id: str,
        name: str,
        weight: float,
    ) -> None:
        info = source.info
        self.id = master_id
        self.name = name
        self.axes = [float(weight)]
        self.capHeight = float(info.capHeight or 0.0)
        self.xHeight = float(info.xHeight or 0.0)
        self.descender = float(info.descender or 0.0)
        # Glyphs uses a positive right-leaning design angle. UFO/OpenType
        # metadata stores the same right lean as a negative italicAngle.
        self.italicAngle = abs(float(info.italicAngle or 0.0))
        self.ufoItalicAngle = float(info.italicAngle or 0.0)
        stem_values = list(info.postscriptStemSnapV or [])
        stem_values.extend(list(info.postscriptStemSnapH or []))
        self.stems = [
            float(value) for value in stem_values if float(value) > 0.0
        ]


class UFOFont:
    """Read-only Glyphs-shaped view of one UFO master."""

    def __init__(
        self,
        path: Path,
        *,
        master_id: str,
        master_name: str,
        weight: float = 400.0,
    ) -> None:
        source = DefconFont(str(path))
        self.sourcePath = Path(path)
        self.upm = float(source.info.unitsPerEm or 1000.0)
        self.axes = [SimpleNamespace(axisTag="wght", tag="wght")]
        master = UFOMaster(
            source,
            master_id=master_id,
            name=master_name,
            weight=weight,
        )
        self.masters = [master]
        self.glyphs = _GlyphProxy(
            {
                str(glyph_name): _Glyph(source[glyph_name], master.id)
                for glyph_name in source.keys()
            }
        )


def load_ufo(
    path: Path,
    *,
    master_id: str,
    master_name: str,
    weight: float = 400.0,
) -> UFOFont:
    if not path.is_dir():
        raise RuntimeError("Pinned UFO source was not found: {}".format(path))
    return UFOFont(
        path,
        master_id=master_id,
        master_name=master_name,
        weight=weight,
    )


def unicode_name_map(font: UFOFont) -> dict[int, str]:
    result: dict[int, str] = {}
    for glyph in font.glyphs:
        for codepoint in glyph.unicodes:
            existing = result.get(codepoint)
            if existing is not None and existing != glyph.name:
                raise RuntimeError(
                    "UFO has multiple glyph names for U+{:04X}: {}, {}".format(
                        codepoint,
                        existing,
                        glyph.name,
                    )
                )
            result[codepoint] = glyph.name
    return result
