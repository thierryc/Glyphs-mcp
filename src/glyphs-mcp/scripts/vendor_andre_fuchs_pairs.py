#!/usr/bin/env python3
# encoding: utf-8

"""Vendor Andre Fuchs' kerning-pairs export into the Glyphs MCP plugin bundle.

This script is intentionally "best effort": it accepts a variety of upstream
export shapes (JSON or text) and normalizes them into the compact dataset format
consumed by the MCP tool.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple


def _parse_pair_fields(fields: Sequence[str]) -> Optional[Tuple[str, str]]:
    if len(fields) < 2:
        return None
    left = fields[0].strip()
    right = fields[1].strip()
    if len(left) == 1 and len(right) == 1:
        return left, right
    return None


def _parse_pair_string(raw: str) -> Optional[Tuple[str, str]]:
    s = (raw or "").strip()
    if not s:
        return None

    # Common case: "A V ..." or "A\tV\t..."
    parts = s.split()
    pair = _parse_pair_fields(parts)
    if pair:
        return pair

    # Common case: "AV"
    if len(s) == 2:
        return s[0], s[1]

    # Loose: "A,V" / "A-V" / "A:V"
    m = re.match(r"^(.)(?:,|-|:|;)(.)$", s)
    if m:
        return m.group(1), m.group(2)

    return None


def _iter_pairs_from_text(path: Path) -> Iterator[Tuple[str, str]]:
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pair = _parse_pair_string(line)
        if pair:
            yield pair


def _pairs_from_mapping(obj: Dict[Any, Any]) -> Iterator[Tuple[str, str]]:
    for key, value in obj.items():
        # Key is often a pair string (e.g. "AV")
        if isinstance(key, str):
            pair = _parse_pair_string(key)
            if pair:
                yield pair

        # Value may itself contain a pair representation.
        if isinstance(value, dict):
            left = value.get("left")
            right = value.get("right")
            if isinstance(left, str) and isinstance(right, str):
                pair = _parse_pair_fields([left, right])
                if pair:
                    yield pair
            pair_value = value.get("pair")
            if isinstance(pair_value, str):
                pair = _parse_pair_string(pair_value)
                if pair:
                    yield pair


def _pairs_from_iterable(obj: Sequence[Any]) -> Iterator[Tuple[str, str]]:
    for item in obj:
        if isinstance(item, str):
            pair = _parse_pair_string(item)
            if pair:
                yield pair
            continue

        if isinstance(item, (list, tuple)) and len(item) >= 2:
            left = item[0]
            right = item[1]
            if isinstance(left, str) and isinstance(right, str):
                pair = _parse_pair_fields([left, right])
                if pair:
                    yield pair
            continue

        if isinstance(item, dict):
            left = item.get("left")
            right = item.get("right")
            if isinstance(left, str) and isinstance(right, str):
                pair = _parse_pair_fields([left, right])
                if pair:
                    yield pair
            pair_value = item.get("pair")
            if isinstance(pair_value, str):
                pair = _parse_pair_string(pair_value)
                if pair:
                    yield pair
            continue


def _iter_pairs_from_json(obj: Any) -> Iterator[Tuple[str, str]]:
    if isinstance(obj, dict):
        pairs_value = obj.get("pairs")
        if isinstance(pairs_value, list):
            yield from _pairs_from_iterable(pairs_value)
        yield from _pairs_from_mapping(obj)
        return

    if isinstance(obj, list):
        yield from _pairs_from_iterable(obj)
        return


def _dedupe_preserve_order(pairs: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    seen: set[Tuple[str, str]] = set()
    for left, right in pairs:
        item = (left, right)
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _output_dir() -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    return (
        repo_root
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
        / "kerning_data"
        / "andre_fuchs"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Path to an Andre-Fuchs export (JSON or TXT).")
    parser.add_argument("--commit", default="unknown", help="Upstream commit hash (optional).")
    parser.add_argument("--repo", default="https://github.com/andre-fuchs/kerning-pairs", help="Source repo URL.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report, but do not write files.")
    args = parser.parse_args(argv)

    in_path = Path(args.input).expanduser().resolve()
    if not in_path.exists():
        print("Input file not found: {}".format(in_path), file=sys.stderr)
        return 2

    pairs: List[Tuple[str, str]] = []
    if in_path.suffix.lower() in (".json",):
        try:
            obj = json.loads(in_path.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:
            print("Failed to parse JSON: {}".format(exc), file=sys.stderr)
            return 2
        pairs = _dedupe_preserve_order(_iter_pairs_from_json(obj))
    else:
        pairs = _dedupe_preserve_order(_iter_pairs_from_text(in_path))

    if not pairs:
        print("No pairs found in {}".format(in_path), file=sys.stderr)
        return 2

    payload = {
        "id": "andre_fuchs_relevant_pairs",
        "source": {
            "repo": args.repo,
            "license": "MIT",
            "commit": args.commit,
            "retrievedAt": date.today().isoformat(),
        },
        "pairs": [{"left": left, "right": right} for left, right in pairs],
    }

    out_dir = _output_dir()
    out_json = out_dir / "relevant_pairs.v1.json"
    out_attr = out_dir / "ATTRIBUTION.md"
    out_license = out_dir / "LICENSE.txt"

    if args.dry_run:
        print("Parsed {} pairs from {}".format(len(pairs), in_path))
        print("Would write {}".format(out_json))
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    out_attr.write_text(
        "\n".join(
            [
                "# Andre Fuchs kerning-pairs (MIT) — bundled snapshot",
                "",
                "Source repository: {}".format(args.repo),
                "Upstream commit: {}".format(args.commit),
                "Generated on: {}".format(payload["source"]["retrievedAt"]),
                "Input file: {}".format(in_path),
                "",
                "This file was generated by:",
                "`{}`".format(Path(__file__).name),
                "",
                "Normalization:",
                "- extracted (left,right) as single Unicode characters where possible",
                "- deduplicated while preserving order",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    out_license.write_text(
        "\n".join(
            [
                "MIT License",
                "",
                "This dataset snapshot is derived from:",
                args.repo,
                "",
                "Copyright (c) Andre Fuchs",
                "",
                "Permission is hereby granted, free of charge, to any person obtaining a copy",
                'of this software and associated documentation files (the "Software"), to deal',
                "in the Software without restriction, including without limitation the rights",
                "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell",
                "copies of the Software, and to permit persons to whom the Software is",
                "furnished to do so, subject to the following conditions:",
                "",
                "The above copyright notice and this permission notice shall be included in all",
                "copies or substantial portions of the Software.",
                "",
                'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR',
                "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,",
                "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE",
                "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER",
                "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,",
                "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE",
                "SOFTWARE.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print("Wrote {}".format(out_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
