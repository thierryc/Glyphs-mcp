#!/usr/bin/env python3
"""Backward-compatible entry point for documentation generation.

The documentation source now comes directly from the pinned official
GlyphsSDK submodule. Use ``generate_documentation.py`` for new workflows.
"""

from generate_documentation import main


if __name__ == "__main__":
    raise SystemExit(main())
