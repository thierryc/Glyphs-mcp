# encoding: utf-8

"""Sample MCP prompts for interacting with Glyphs tools."""

from __future__ import division, print_function, unicode_literals

from fastmcp.prompts.prompt import Message

from mcp_tools import mcp


@mcp.prompt(
    name="print_master_names",
    title="Print Master Names",
    description="Guide the assistant to list master names using the font master tool.",
    tags={"examples", "glyphs"},
)
async def prompt_print_master_names():
    """Prompt describing how to print master names for the active font."""
    return [
        Message(
            "Use glyphs-app-mcp__get_font_masters to print master names for the active font.",
            role="user",
        )
    ]


@mcp.prompt(
    name="list_current_glyph_nodes",
    title="List Current Glyph Nodes",
    description="Instructs the assistant to list node coordinates for the selected glyph.",
    tags={"examples", "glyphs"},
)
async def prompt_list_current_glyph_nodes():
    """Prompt describing how to inspect node positions via execute_code_with_context."""
    return [
        Message(
            "Call glyphs-app-mcp__execute_code_with_context to list the current glyph's node coordinates.",
            role="user",
        )
    ]


@mcp.prompt(
    name="add_acute_component",
    title="Add Acute Component",
    description="Shows how to add an acute component to the glyph A at a specific offset.",
    tags={"examples", "glyphs"},
)
async def prompt_add_acute_component():
    """Prompt describing how to add a component to glyph A."""
    return [
        Message(
            "Run glyphs-app-mcp__add_component_to_glyph to place component acute on glyph A at offset (0, 120).",
            role="user",
        )
    ]


@mcp.prompt(
    name="report_tightest_kerning_pairs",
    title="Report Tightest Kerning Pairs",
    description="Encourages inspecting kerning data and summarising the smallest values.",
    tags={"examples", "glyphs"},
)
async def prompt_report_tightest_kerning_pairs():
    """Prompt describing how to inspect kerning for tight pairs."""
    return [
        Message(
            "Fetch kerning via glyphs-app-mcp__get_font_kerning and report the tightest pairs.",
            role="user",
        )
    ]


@mcp.prompt(
    name="recalculate_sidebearings",
    title="Recalculate Sidebearings",
    description="Suggests executing Python to recalculate sidebearings for selected glyphs.",
    tags={"examples", "glyphs"},
)
async def prompt_recalculate_sidebearings():
    """Prompt describing how to recalculate sidebearings using a Python script."""
    return [
        Message(
            "Execute Python that recalculates sidebearings for selected glyphs; show the script output.",
            role="user",
        )
    ]


@mcp.prompt(
    name="copy_and_translate_ae_paths",
    title="Copy and Translate ae Paths",
    description="Walks through copying background paths for the ligature ae and translating the e component.",
    tags={"examples", "glyphs"},
)
async def prompt_copy_and_translate_ae_paths():
    """Prompt describing how to copy and translate background paths for the ae glyph."""
    return [
        Message(
            "In Glyphs, copy the path of the \"a\" and \"e\" in the background of the letter \"ae\" in every master.",
            role="user",
        ),
        Message(
            "Translate the path of the \"e\" aligned on the right of the letter \"ae\".",
            role="user",
        ),
    ]


@mcp.prompt(
    name="selected_nodes_and_insert_point",
    title="Selected Nodes + Insert Point",
    description="Retrieve selected nodes and demonstrate inserting a point before them across masters.",
    tags={"examples", "glyphs"},
)
async def prompt_selected_nodes_and_insert_point():
    """Prompt showing how to use get_selected_nodes and follow up with code execution."""
    return [
        Message(
            "Call glyphs-app-mcp__get_selected_nodes. Using its mapping, generate Python that inserts a point just before each selected node on all masters of the same glyph.",
            role="user",
        )
    ]
