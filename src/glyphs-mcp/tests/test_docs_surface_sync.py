"""Guards against documentation drift for the MCP tool surface.

We avoid importing the tool modules because they import GlyphsApp (not present
in the normal unit test runner). Instead, we extract tool names from source
text by looking for @mcp.tool() followed by an async def.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


def _repo_root() -> Path:
    # .../src/glyphs-mcp/tests/test_*.py -> repo root is 3 parents up.
    return Path(__file__).resolve().parents[3]


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


def _tool_source_paths() -> list[Path]:
    resources = _resources_dir()
    paths = sorted(resources.glob("mcp_tools_*.py"))
    paths.append(resources / "code_execution.py")
    paths.append(resources / "docs_tools.py")
    return [p for p in paths if p.is_file()]


def _extract_tool_names(paths: list[Path]) -> set[str]:
    tool_names: set[str] = set()
    for path in paths:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if line.strip() != "@mcp.tool()":
                continue
            for j in range(i + 1, min(i + 12, len(lines))):
                match = re.match(r"^\s*async def (\w+)\s*\(", lines[j])
                if match:
                    tool_names.add(match.group(1))
                    break
    return tool_names


def _read_readme_command_set_section(readme_text: str) -> str:
    header = re.search(r"^##\s+Command Set\s+\(MCP server v[^\)]+\)\s*$", readme_text, re.M)
    if not header:
        raise AssertionError("README Command Set header not found.")

    # Find the next H2 heading after the command set header.
    rest = readme_text[header.end() :]
    next_header = re.search(r"^##\s+", rest, re.M)
    if next_header:
        return rest[: next_header.start()]
    return rest


class DocsSurfaceSyncTests(unittest.TestCase):
    def test_command_set_mdx_mentions_all_tools(self) -> None:
        tool_names = _extract_tool_names(_tool_source_paths())
        self.assertGreater(len(tool_names), 0, "Expected at least one tool name to be discovered.")

        command_set = _repo_root() / "content" / "reference" / "command-set.mdx"
        self.assertTrue(command_set.is_file(), f"Missing docs page: {command_set}")
        text = command_set.read_text(encoding="utf-8", errors="replace")

        missing = sorted([name for name in tool_names if name not in text])
        self.assertEqual(missing, [], f"command-set.mdx is missing tool names: {missing}")

    def test_readme_command_set_mentions_all_tools(self) -> None:
        tool_names = _extract_tool_names(_tool_source_paths())
        self.assertGreater(len(tool_names), 0, "Expected at least one tool name to be discovered.")

        readme = _repo_root() / "README.md"
        self.assertTrue(readme.is_file(), f"Missing README: {readme}")
        readme_text = readme.read_text(encoding="utf-8", errors="replace")
        section = _read_readme_command_set_section(readme_text)

        missing = sorted([name for name in tool_names if name not in section])
        self.assertEqual(missing, [], f"README Command Set section is missing tool names: {missing}")


if __name__ == "__main__":
    unittest.main()

