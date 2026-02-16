"""Guards against shipping unregistered MCP tools.

These tests are intentionally text-based because the MCP tool module imports
GlyphsApp, which is not available in the normal unit test runner.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


class McpToolRegistrationTextTests(unittest.TestCase):
    def test_set_spacing_params_is_decorated(self) -> None:
        mcp_tools = (
            Path(__file__).resolve().parent.parent
            / "Glyphs MCP.glyphsPlugin"
            / "Contents"
            / "Resources"
            / "mcp_tools.py"
        )
        text = mcp_tools.read_text(encoding="utf-8", errors="replace")
        pattern = re.compile(r"@mcp\.tool\(\)\s*\nasync def set_spacing_params\s*\(", re.M)
        self.assertRegex(text, pattern)


if __name__ == "__main__":
    unittest.main()

