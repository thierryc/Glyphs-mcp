"""Font-unit comparisons for proposals and display, never exact restoration."""
from math import isclose

GEOMETRY_TOLERANCE = 0.001


def same_font_units(left, right):
    return isclose(left, right, rel_tol=0, abs_tol=GEOMETRY_TOLERANCE)
