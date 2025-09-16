#!/usr/bin/env python3
"""Generate reStructuredText files for the MCP server.

The script extracts triple-quoted documentation blocks from
``GlyphsApp/__init__.py``. Each block is written to a
``section_*.rst`` file inside ``docs/`` (ignored by Git) and recorded in
``index.json`` for lightweight lookup.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def extract_sections(init_path: Path) -> list[str]:
    """Return a list of documentation sections from ``init_path``."""
    content = init_path.read_text(encoding="utf-8")
    return [part.strip() for part in re.findall(r"'''(.*?)'''", content, re.DOTALL)]


def generate_docs() -> None:
    """Write section files into ``docs/`` and an ``index.json`` map."""
    root = Path(__file__).resolve().parent
    init_file = root.parent / "GlyphsApp" / "__init__.py"
    sections = extract_sections(init_file)
    if not sections:
        raise SystemExit("No documentation blocks found")

    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    index: dict[str, str] = {}
    for i, section in enumerate(sections, start=1):
        name = f"section_{i}"
        (docs_dir / f"{name}.rst").write_text(section + "\n", encoding="utf-8")
        first_line = section.strip().splitlines()[0]
        index[name] = first_line

    (root / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {len(sections)} sections to {docs_dir} and index.json")


if __name__ == "__main__":
    generate_docs()
