#!/usr/bin/env python3
"""Expanded clean-room italic benchmark for Inter and Noto Sans.

The benchmark covers the complete Latin uppercase and lowercase alphabets,
all ten lining figures, and four retained punctuation/diacritic cases. Pinned
font sources remain beneath the ignored benchmark cache and are never modified
or committed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import benchmark_italic_inter as base


NOTO_SANS_COMMIT = "cb097900c74b26e6dcab899b4f07b2bc79dd80c4"
UPPERCASE_GLYPHS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
LOWERCASE_GLYPHS = list("abcdefghijklmnopqrstuvwxyz")
NUMERAL_GLYPHS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
]
EXTRA_GLYPHS = ["parenleft", "ampersand", "adieresis", "iacute"]
GLYPH_GROUPS = {
    "uppercase": UPPERCASE_GLYPHS,
    "lowercase": LOWERCASE_GLYPHS,
    "numerals": NUMERAL_GLYPHS,
    "extras": EXTRA_GLYPHS,
}
GLYPHS = [
    glyph_name
    for group in GLYPH_GROUPS.values()
    for glyph_name in group
]


def _mode_labels(family_name: str) -> list[tuple[str, str]]:
    return [
        ("roman", "{} Roman".format(family_name)),
        ("raw", "Raw"),
        ("cursivy", "Cursivy"),
        ("balanced", "Balanced"),
        ("official", "Official {} Italic".format(family_name)),
    ]


def _group_summary(
    glyph_rows: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    rows_by_name = {row["glyphName"]: row for row in glyph_rows}
    summary = {}
    for group_name, glyph_names in GLYPH_GROUPS.items():
        rows = [rows_by_name[glyph_name] for glyph_name in glyph_names]
        summary[group_name] = {
            "glyphCount": len(rows),
            "topologyPreservedCount": len(
                [row for row in rows if row["topologyPreserved"]]
            ),
            "compensatedPairCount": sum(
                int(row["compensatedPairCount"]) for row in rows
            ),
        }
    return summary


def _require_matching_angle(result: dict[str, Any], expected_angle: float) -> None:
    official_angle = float(result["source"]["italicMaster"]["italicAngle"])
    if abs(official_angle - expected_angle) > 0.01:
        raise RuntimeError(
            "Official italic angle {} does not match requested angle {}".format(
                official_angle,
                expected_angle,
            )
        )


def run(inter_root: Path, noto_root: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    inter = base.benchmark_family(
        family_name="Inter",
        roman_path=inter_root / "src" / "Inter-Roman.glyphspackage",
        italic_path=inter_root / "src" / "Inter-Italic.glyphspackage",
        expected_axes={"opsz": 14, "wght": 400},
        glyphs=GLYPHS,
        angle=9.4,
        png_path=output_dir / "italic-balanced-inter-v4.1-expanded.png",
        mode_labels=_mode_labels("Inter"),
        normalize_upm=True,
    )
    noto = base.benchmark_family(
        family_name="Noto Sans",
        roman_path=noto_root / "sources" / "NotoSans.glyphspackage",
        italic_path=noto_root / "sources" / "NotoSans-Italic.glyphspackage",
        expected_axes={"wght": 90, "wdth": 100},
        glyphs=GLYPHS,
        angle=12.0,
        png_path=output_dir
        / "italic-balanced-noto-sans-{}-expanded.png".format(
            NOTO_SANS_COMMIT[:8]
        ),
        mode_labels=_mode_labels("Noto Sans"),
        normalize_upm=True,
    )
    _require_matching_angle(inter, 9.4)
    _require_matching_angle(noto, 12.0)
    inter["source"].update(
        {
            "repository": "https://github.com/rsms/inter",
            "commit": base.INTER_COMMIT,
            "externalAxes": {"opsz": 14, "wght": 400},
        }
    )
    noto["source"].update(
        {
            "repository": "https://github.com/notofonts/latin-greek-cyrillic",
            "googleFonts": "https://github.com/google/fonts/tree/main/ofl/notosans",
            "commit": NOTO_SANS_COMMIT,
            "sourceAxes": {"wght": 90, "wdth": 100},
            "externalAxes": {"wght": 400, "wdth": 100},
        }
    )
    for family_result in (inter, noto):
        family_result["groupSummary"] = _group_summary(family_result["glyphs"])
    family_acceptance = {
        "inter": all(inter["acceptance"].values()),
        "notoSans": all(noto["acceptance"].values()),
    }
    result = {
        "settings": {
            "glyphCountPerFamily": len(GLYPHS),
            "glyphGroups": GLYPH_GROUPS,
            "origin": base.ORIGIN,
            "curveStrength": base.CURVE_STRENGTH,
            "stemCompensation": base.STEM_COMPENSATION,
            "cursivyFallbackStemStrength": (
                base.engine.CURSIVY_FALLBACK_STEM_STRENGTH
            ),
        },
        "families": {
            "inter": inter,
            "notoSans": noto,
        },
        "acceptance": {
            **family_acceptance,
            "allFamiliesPass": all(family_acceptance.values()),
        },
    }
    json_path = output_dir / "benchmark-results-expanded-sans.json"
    result["artifacts"] = {
        "json": str(json_path),
        "interPng": inter["artifacts"]["png"],
        "notoSansPng": noto["artifacts"]["png"],
    }
    json_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    cache_root = base._repo_root() / ".cache" / "italic-benchmark"
    parser.add_argument(
        "--inter-root",
        type=Path,
        default=cache_root / "inter-{}".format(base.INTER_COMMIT),
    )
    parser.add_argument(
        "--noto-root",
        type=Path,
        default=cache_root
        / "noto-sans-{}".format(NOTO_SANS_COMMIT),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=cache_root / "results-expanded",
    )
    args = parser.parse_args()
    result = run(
        args.inter_root.resolve(),
        args.noto_root.resolve(),
        args.output_dir.resolve(),
    )
    print(
        json.dumps(
            {
                "summaries": {
                    family_name: family["summary"]
                    for family_name, family in result["families"].items()
                },
                "acceptance": result["acceptance"],
                "artifacts": result["artifacts"],
            },
            indent=2,
        )
    )
    return 0 if result["acceptance"]["allFamiliesPass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
