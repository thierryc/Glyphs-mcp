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
        lines = mcp_tools.read_text(encoding="utf-8", errors="replace").splitlines()

        def strip_comment(line: str) -> str:
            return line.split("#", 1)[0].strip()

        def prev_significant_line(start_index: int) -> tuple[int, str] | tuple[None, None]:
            for i in range(start_index - 1, -1, -1):
                s = strip_comment(lines[i])
                if not s:
                    continue
                return i, s
            return None, None

        target_idx = None
        for i, line in enumerate(lines):
            if re.match(r"^\s*async def set_spacing_params\s*\(", line):
                target_idx = i
                break

        self.assertIsNotNone(target_idx, "Expected to find async def set_spacing_params(...) in mcp_tools.py")

        i1, prev1 = prev_significant_line(target_idx)  # type: ignore[arg-type]
        self.assertEqual(prev1, "@mcp.tool()", "set_spacing_params must be decorated with @mcp.tool()")

        i2, prev2 = prev_significant_line(i1)  # type: ignore[arg-type]
        self.assertNotEqual(prev2, "@mcp.tool()", "set_spacing_params must not be double-decorated with @mcp.tool()")

    def test_generate_kerning_tab_is_decorated(self) -> None:
        mcp_tools = (
            Path(__file__).resolve().parent.parent
            / "Glyphs MCP.glyphsPlugin"
            / "Contents"
            / "Resources"
            / "mcp_tools.py"
        )
        lines = mcp_tools.read_text(encoding="utf-8", errors="replace").splitlines()

        def strip_comment(line: str) -> str:
            return line.split("#", 1)[0].strip()

        def prev_significant_line(start_index: int) -> tuple[int, str] | tuple[None, None]:
            for i in range(start_index - 1, -1, -1):
                s = strip_comment(lines[i])
                if not s:
                    continue
                return i, s
            return None, None

        target_idx = None
        for i, line in enumerate(lines):
            if re.match(r"^\s*async def generate_kerning_tab\s*\(", line):
                target_idx = i
                break

        self.assertIsNotNone(target_idx, "Expected to find async def generate_kerning_tab(...) in mcp_tools.py")

        i1, prev1 = prev_significant_line(target_idx)  # type: ignore[arg-type]
        self.assertEqual(prev1, "@mcp.tool()", "generate_kerning_tab must be decorated with @mcp.tool()")

        i2, prev2 = prev_significant_line(i1)  # type: ignore[arg-type]
        self.assertNotEqual(prev2, "@mcp.tool()", "generate_kerning_tab must not be double-decorated with @mcp.tool()")

    def test_review_kerning_bumper_is_decorated(self) -> None:
        mcp_tools = (
            Path(__file__).resolve().parent.parent
            / "Glyphs MCP.glyphsPlugin"
            / "Contents"
            / "Resources"
            / "mcp_tools.py"
        )
        lines = mcp_tools.read_text(encoding="utf-8", errors="replace").splitlines()

        def strip_comment(line: str) -> str:
            return line.split("#", 1)[0].strip()

        def prev_significant_line(start_index: int) -> tuple[int, str] | tuple[None, None]:
            for i in range(start_index - 1, -1, -1):
                s = strip_comment(lines[i])
                if not s:
                    continue
                return i, s
            return None, None

        target_idx = None
        for i, line in enumerate(lines):
            if re.match(r"^\s*async def review_kerning_bumper\s*\(", line):
                target_idx = i
                break

        self.assertIsNotNone(target_idx, "Expected to find async def review_kerning_bumper(...) in mcp_tools.py")

        i1, prev1 = prev_significant_line(target_idx)  # type: ignore[arg-type]
        self.assertEqual(prev1, "@mcp.tool()", "review_kerning_bumper must be decorated with @mcp.tool()")

        i2, prev2 = prev_significant_line(i1)  # type: ignore[arg-type]
        self.assertNotEqual(prev2, "@mcp.tool()", "review_kerning_bumper must not be double-decorated with @mcp.tool()")

    def test_apply_kerning_bumper_is_decorated(self) -> None:
        mcp_tools = (
            Path(__file__).resolve().parent.parent
            / "Glyphs MCP.glyphsPlugin"
            / "Contents"
            / "Resources"
            / "mcp_tools.py"
        )
        lines = mcp_tools.read_text(encoding="utf-8", errors="replace").splitlines()

        def strip_comment(line: str) -> str:
            return line.split("#", 1)[0].strip()

        def prev_significant_line(start_index: int) -> tuple[int, str] | tuple[None, None]:
            for i in range(start_index - 1, -1, -1):
                s = strip_comment(lines[i])
                if not s:
                    continue
                return i, s
            return None, None

        target_idx = None
        for i, line in enumerate(lines):
            if re.match(r"^\s*async def apply_kerning_bumper\s*\(", line):
                target_idx = i
                break

        self.assertIsNotNone(target_idx, "Expected to find async def apply_kerning_bumper(...) in mcp_tools.py")

        i1, prev1 = prev_significant_line(target_idx)  # type: ignore[arg-type]
        self.assertEqual(prev1, "@mcp.tool()", "apply_kerning_bumper must be decorated with @mcp.tool()")

        i2, prev2 = prev_significant_line(i1)  # type: ignore[arg-type]
        self.assertNotEqual(prev2, "@mcp.tool()", "apply_kerning_bumper must not be double-decorated with @mcp.tool()")


if __name__ == "__main__":
    unittest.main()
