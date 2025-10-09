#!/usr/bin/env python3
"""
Wrapper entrypoint for the interactive Glyphs MCP installer.

Usage:
  python3 install.py
"""
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "src" / "glyphs-mcp" / "scripts" / "install_cli.py"

if not SCRIPT.exists():
    raise SystemExit(f"Installer script not found at: {SCRIPT}")

# Execute the real installer as __main__ so it behaves like a direct run
runpy.run_path(str(SCRIPT), run_name="__main__")

