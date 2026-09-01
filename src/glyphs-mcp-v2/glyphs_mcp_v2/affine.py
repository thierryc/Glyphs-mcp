"""Shared affine synthesis and deterministic component decomposition."""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Sequence


AFFINE_EPSILON = 1e-12


def component_matrix(value: Mapping[str, Any]) -> Optional[list[float]]:
    """Synthesize one affine matrix from Glyphs' saved decomposition."""

    position = value.get("position")
    scale = value.get("scale", (1, 1))
    slant = value.get("slant", (0, 0))
    if not all(
        isinstance(item, (list, tuple)) and len(item) == 2
        for item in (position, scale, slant)
    ):
        return None
    try:
        px, py = (float(position[0]), float(position[1]))
        sx, sy = (float(scale[0]), float(scale[1]))
        slant_x, slant_y = (float(slant[0]), float(slant[1]))
        angle = math.radians(float(value.get("angle") or 0))
    except (TypeError, ValueError):
        return None
    values = (px, py, sx, sy, slant_x, slant_y, angle)
    if not all(math.isfinite(item) for item in values):
        return None
    horizontal_slant = math.tan(math.radians(slant_x))
    vertical_slant = math.tan(math.radians(slant_y))
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return [
        sx * (cosine - sine * vertical_slant),
        sx * (sine + cosine * vertical_slant),
        sy * (horizontal_slant * cosine - sine),
        sy * (horizontal_slant * sine + cosine),
        px,
        py,
    ]


def matrix_multiply(
    left: Sequence[float], right: Sequence[float]
) -> tuple[float, float, float, float, float, float]:
    la, lb, lc, ld, ltx, lty = left
    ra, rb, rc, rd, rtx, rty = right
    return (
        la * ra + lc * rb,
        lb * ra + ld * rb,
        la * rc + lc * rd,
        lb * rc + ld * rd,
        la * rtx + lc * rty + ltx,
        lb * rtx + ld * rty + lty,
    )


def matrix_inverse(
    value: Sequence[float],
) -> tuple[float, float, float, float, float, float]:
    a, b, c, d, tx, ty = value
    determinant = a * d - b * c
    if abs(determinant) <= AFFINE_EPSILON:
        raise ValueError("conjugate transforms require an invertible matrix")
    return (
        d / determinant,
        -b / determinant,
        -c / determinant,
        a / determinant,
        (c * ty - d * tx) / determinant,
        (b * tx - a * ty) / determinant,
    )


def matrix_about_origin(
    value: Sequence[float], origin: Sequence[float]
) -> tuple[float, float, float, float, float, float]:
    if not isinstance(origin, (list, tuple)) or len(origin) != 2:
        raise ValueError("transform.origin must contain two finite numbers")
    ox, oy = float(origin[0]), float(origin[1])
    if not math.isfinite(ox) or not math.isfinite(oy):
        raise ValueError("transform.origin must contain two finite numbers")
    return matrix_multiply(
        (1.0, 0.0, 0.0, 1.0, ox, oy),
        matrix_multiply(
            value,
            (1.0, 0.0, 0.0, 1.0, -ox, -oy),
        ),
    )


def matrices_close(left: Sequence[float], right: Sequence[float]) -> bool:
    return all(
        math.isclose(a, b, rel_tol=1e-12, abs_tol=AFFINE_EPSILON)
        for a, b in zip(left, right)
    )


def clean_float(value: float) -> int | float:
    """Canonicalize exact integers without snapping a nonzero fraction."""

    if value == 0.0:
        return 0
    if float(value).is_integer():
        return int(value)
    return float(value)


def decompose_component_matrix(value: Sequence[float]) -> dict[str, Any]:
    """Return one deterministic Glyphs component decomposition."""

    a, b, c, d, tx, ty = value
    scale_x = math.hypot(a, b)
    determinant = a * d - b * c
    if scale_x <= AFFINE_EPSILON or abs(determinant) <= AFFINE_EPSILON:
        raise ValueError("component transforms must remain invertible")
    cosine = a / scale_x
    sine = b / scale_x
    scale_y = determinant / scale_x
    horizontal_slant = (c * cosine + d * sine) / scale_y
    return {
        "position": [clean_float(tx), clean_float(ty)],
        "scale": [clean_float(scale_x), clean_float(scale_y)],
        "angle": clean_float(math.degrees(math.atan2(sine, cosine))),
        "slant": [
            clean_float(math.degrees(math.atan(horizontal_slant))),
            0,
        ],
    }


def require_component_matrix(value: Mapping[str, Any]) -> tuple[float, ...]:
    """Validate that a canonical component decomposition is replayable."""

    matrix = component_matrix(value)
    if matrix is None:
        raise ValueError("component transform decomposition is invalid")
    determinant = matrix[0] * matrix[3] - matrix[1] * matrix[2]
    if abs(determinant) <= AFFINE_EPSILON:
        raise ValueError("component transforms must remain invertible")
    return tuple(matrix)


__all__ = [
    "AFFINE_EPSILON",
    "clean_float",
    "component_matrix",
    "decompose_component_matrix",
    "matrices_close",
    "matrix_about_origin",
    "matrix_inverse",
    "matrix_multiply",
    "require_component_matrix",
]
