"""Offline stdio entry point for clients without local HTTP transport."""
import sys
from fastmcp import FastMCP


def main():
    FastMCP.as_proxy(sys.argv[1], name="Glyphs MCP").run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
