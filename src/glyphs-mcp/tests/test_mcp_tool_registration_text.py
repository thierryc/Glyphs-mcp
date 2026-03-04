"""Guards against shipping unregistered MCP tools.

These tests are intentionally text-based because the MCP tool module imports
GlyphsApp, which is not available in the normal unit test runner.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


def _tool_module_paths() -> list[Path]:
    resources = _resources_dir()
    return sorted(resources.glob("mcp_tools_*.py"))


class McpToolRegistrationTextTests(unittest.TestCase):
    def test_gscomponent_automatic_is_compat_safe(self) -> None:
        resources = _resources_dir()
        paths = [resources / "mcp_tool_helpers.py"] + _tool_module_paths()
        text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in paths if p.is_file())
        self.assertIsNone(
            re.search(r"\"automatic\"\\s*:\\s*component\\.automatic\\b", text),
            "Tool modules must not access GSComponent.automatic directly; use a compatibility helper.",
        )

    def _assert_async_tool_decorated(self, function_name: str) -> None:
        tool_files = _tool_module_paths()
        self.assertGreater(len(tool_files), 0, "Expected at least one mcp_tools_*.py tool module")

        found_path: Path | None = None
        found_lines: list[str] | None = None
        found_index: int | None = None

        for path in tool_files:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines):
                if re.match(rf"^\s*async def {re.escape(function_name)}\s*\(", line):
                    found_path = path
                    found_lines = lines
                    found_index = i
                    break
            if found_path is not None:
                break

        def strip_comment(line: str) -> str:
            return line.split("#", 1)[0].strip()

        def prev_significant_line(start_index: int) -> tuple[int, str] | tuple[None, None]:
            assert found_lines is not None
            for i in range(start_index - 1, -1, -1):
                s = strip_comment(found_lines[i])
                if not s:
                    continue
                return i, s
            return None, None

        self.assertIsNotNone(
            found_index,
            f"Expected to find async def {function_name}(...) in one of: {[p.name for p in tool_files]}",
        )
        assert found_index is not None
        assert found_path is not None

        i1, prev1 = prev_significant_line(found_index)
        self.assertEqual(
            prev1,
            "@mcp.tool()",
            f"{function_name} must be decorated with @mcp.tool() (found in {found_path.name})",
        )

        i2, prev2 = prev_significant_line(i1)  # type: ignore[arg-type]
        self.assertNotEqual(
            prev2,
            "@mcp.tool()",
            f"{function_name} must not be double-decorated with @mcp.tool() (found in {found_path.name})",
        )

    def test_set_spacing_params_is_decorated(self) -> None:
        self._assert_async_tool_decorated("set_spacing_params")

    def test_generate_kerning_tab_is_decorated(self) -> None:
        self._assert_async_tool_decorated("generate_kerning_tab")

    def test_review_kerning_bumper_is_decorated(self) -> None:
        self._assert_async_tool_decorated("review_kerning_bumper")

    def test_apply_kerning_bumper_is_decorated(self) -> None:
        self._assert_async_tool_decorated("apply_kerning_bumper")

    def test_compensated_tuning_tools_are_decorated(self) -> None:
        self._assert_async_tool_decorated("measure_stem_ratio")
        self._assert_async_tool_decorated("review_compensated_tuning")
        self._assert_async_tool_decorated("apply_compensated_tuning")


if __name__ == "__main__":
    unittest.main()
