from pathlib import Path
from fastmcp import Resource
from mcp_tools import mcp

DOC_ROOT = Path(__file__).parent / "docs"


@mcp.resource("glyphsdoc:///python/overview")
async def python_overview():
    text = (DOC_ROOT / "python/overview.md").read_text(encoding="utf-8")
    return Resource(
        uri="glyphsdoc:///python/overview",
        mimeType="text/markdown",
        text=text,
        name="Python scripting overview",
    )


@mcp.resource("glyphsdoc:///python/GSApplication")
async def python_GSApplication():
    text = (DOC_ROOT / "python/GSApplication.md").read_text(encoding="utf-8")
    return Resource(
        uri="glyphsdoc:///python/GSApplication",
        mimeType="text/markdown",
        text=text,
        name="GSApplication class reference",
    )


@mcp.resource("glyphsdoc:///core/GSFont")
async def core_GSFont():
    text = (DOC_ROOT / "core/GSFont.md").read_text(encoding="utf-8")
    return Resource(
        uri="glyphsdoc:///core/GSFont",
        mimeType="text/markdown",
        text=text,
        name="GSFont core reference",
    )


@mcp.resource("glyphsdoc:///guide/py3-upgrade")
async def guide_py3_upgrade():
    text = (DOC_ROOT / "guide/py3-upgrade.md").read_text(encoding="utf-8")
    return Resource(
        uri="glyphsdoc:///guide/py3-upgrade",
        mimeType="text/markdown",
        text=text,
        name="Python 3 upgrade guide",
    )
