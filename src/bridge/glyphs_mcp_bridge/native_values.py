"""Small native value projections shared by bounded bridge reads."""

from typing import Any

from .context import value as _value


def point(value: Any) -> tuple[float, float]:
    x = _value(value, "x", None)
    y = _value(value, "y", None)
    if x is None or y is None:
        origin = _value(value, "origin", None)
        x = _value(origin, "x", 0)
        y = _value(origin, "y", 0)
    return float(x or 0), float(y or 0)


def rect(value: Any) -> dict[str, float] | None:
    if value is None:
        return None
    origin = _value(value, "origin", None)
    size = _value(value, "size", None)
    return {
        "x": float(_value(origin, "x", 0) or 0),
        "y": float(_value(origin, "y", 0) or 0),
        "width": float(_value(size, "width", 0) or 0),
        "height": float(_value(size, "height", 0) or 0),
    }
