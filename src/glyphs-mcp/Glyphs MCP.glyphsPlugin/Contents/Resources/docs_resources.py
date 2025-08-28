from pathlib import Path
from mcp_tools import mcp

DOC_ROOT = Path(__file__).parent / "docs"


@mcp.resource(
    "glyphsdoc:///python/overview",
    name="Python scripting overview",
    mime_type="text/markdown",
)
async def python_overview():
    return (DOC_ROOT / "python/overview.md").read_text(encoding="utf-8")


@mcp.resource(
    "glyphsdoc:///python/GSApplication",
    name="GSApplication class reference",
    mime_type="text/markdown",
)
async def python_GSApplication():
    return (DOC_ROOT / "python/GSApplication.md").read_text(encoding="utf-8")


@mcp.resource(
    "glyphsdoc:///core/GSFont",
    name="GSFont core reference",
    mime_type="text/markdown",
)
async def core_GSFont():
    return (DOC_ROOT / "core/GSFont.md").read_text(encoding="utf-8")


@mcp.resource(
    "glyphsdoc:///guide/py3-upgrade",
    name="Python 3 upgrade guide",
    mime_type="text/markdown",
)
async def guide_py3_upgrade():
    return (DOC_ROOT / "guide/py3-upgrade.md").read_text(encoding="utf-8")
