from pathlib import Path

from fastmcp.resources.types import TextResource as Resource
from mcp_tools import mcp

DOC_ROOT = Path(__file__).parent / "docs"


@mcp.resource(
    "glyphsdoc:///python/overview",
    name="Python scripting overview",
    mime_type="text/markdown",
)
async def python_overview():
    return (DOC_ROOT / "python/overview.md").read_text(encoding="utf-8")



@mcp.resource("glyphsdoc:///python/{class_name}")
async def python_class(class_name: str):
    path = DOC_ROOT / f"python/{class_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"No docs for {class_name}")
    text = path.read_text(encoding="utf-8")
    return Resource(
        uri=f"glyphsdoc:///python/{class_name}",
        mime_type="text/markdown",
        text=text,
        name=f"{class_name} class reference",
    )


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


# Register available class documentation so it appears in resource listings
for _md_path in (DOC_ROOT / "python").glob("*.md"):
    _class = _md_path.stem
    if _class == "overview":
        continue
    mcp.add_resource(
        Resource(
            uri=f"glyphsdoc:///python/{_class}",
            mime_type="text/markdown",
            text=_md_path.read_text(encoding="utf-8"),
            name=f"{_class} class reference",
        )
    )
