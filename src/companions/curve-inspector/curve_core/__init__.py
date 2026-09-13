"""Pure cubic geometry shared by the Reporter and external jobs."""

from .geometry import (
    DEFAULT_LENGTH_SCALE,
    DEFAULT_MAX_LENGTH_EM,
    DEFAULT_SAMPLES_PER_CURVE,
    DEFAULT_STROKE_LIMIT,
    NEGATIVE_RGBA,
    OVERLAY_ALPHA,
    POSITIVE_RGBA,
    analyze_cubic,
    analyze_cubics,
    build_curvature_comb,
    choose_sample_count,
    cubic_point,
    curvature,
    overlay_line_widths,
)

__all__ = [
    "DEFAULT_LENGTH_SCALE",
    "DEFAULT_MAX_LENGTH_EM",
    "DEFAULT_SAMPLES_PER_CURVE",
    "DEFAULT_STROKE_LIMIT",
    "NEGATIVE_RGBA",
    "OVERLAY_ALPHA",
    "POSITIVE_RGBA",
    "analyze_cubic",
    "analyze_cubics",
    "build_curvature_comb",
    "choose_sample_count",
    "cubic_point",
    "curvature",
    "overlay_line_widths",
]
