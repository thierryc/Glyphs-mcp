# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Global to store vendor path for diagnostics
_vendor_path: Optional[Path] = None


def _setup_vendor_path() -> Optional[Path]:
    """Set up sys.path to use the bundled vendor/ directory.

    Returns the vendor path if found, None otherwise.
    """
    plugin_dir = Path(__file__).parent
    vendor_dir = plugin_dir / "vendor"

    if vendor_dir.is_dir():
        vendor_str = str(vendor_dir)
        if vendor_str not in sys.path:
            sys.path.insert(0, vendor_str)
        return vendor_dir

    return None


_vendor_path = _setup_vendor_path()

# Import utility functions and apply fixes
from utils import fix_glyphs_console
import importlib
fix_glyphs_console()

# Import MCP tools (this registers all the tools)
from mcp_tools import mcp

# Import code execution tools (this registers the execution tools)
import code_execution

# Import bundled documentation resources so they are registered with FastMCP
import documentation_resources  # noqa: F401
# Import prompt examples so they are registered
import prompt_examples  # noqa: F401

# Import and initialize the plugin
from glyphs_plugin import MCPBridgePlugin


# ------------------------------------------------------------
# Diagnostics executed before launching the MCP server
# ------------------------------------------------------------
def _resolve_python_executable() -> str:
    """Best-effort detection of the actual Python binary used by Glyphs."""

    version_tag = f"python{sys.version_info.major}.{sys.version_info.minor}"
    module_candidates = ("objc", "site")

    for module_name in module_candidates:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue

        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue

        module_path = Path(module_file).resolve()
        for parent in module_path.parents:
            if parent.name == version_tag and parent.parent.name == "lib":
                python_root = parent.parent.parent
                binary_name = f"python{sys.version_info.major}.{sys.version_info.minor}"
                candidate = python_root / "bin" / binary_name
                if not candidate.exists():
                    candidate = python_root / "bin" / f"python{sys.version_info.major}"
                if candidate.exists():
                    return str(candidate)

    # Fallback to whatever Glyphs reports (usually the app bundle path)
    return sys.executable


def _check_dependency(name: str) -> Tuple[str, bool, str]:
    """Try to import a dependency and report its status.

    Returns a tuple: (module_name, ok, details)
    details contains the version and file path when available, or the error.
    """
    try:
        module = importlib.import_module(name)
        # Try to get version info
        version = getattr(module, "__version__", None)
        if not version:
            try:
                import importlib.metadata as _md  # Python 3.8+

                # Map import name to distribution name if needed
                dist_name = {
                    "sse_starlette": "sse-starlette",
                    "typing_extensions": "typing-extensions",
                }.get(name, name.replace("_", "-"))
                version = _md.version(dist_name)
            except Exception:
                version = "unknown"
        details = "version: {} at {}".format(version, getattr(module, "__file__", "?"))
        return (name, True, details)
    except Exception as e:  # pragma: no cover - environment dependent
        return (name, False, str(e))


def run_diagnostics() -> None:
    """Print diagnostics, verify dependencies, and display current Python path.

    This runs quickly and safely; failures never raise and won't block startup.
    """
    try:
        # Formatting helpers
        width = 72
        line = "=" * width
        use_color = bool(os.environ.get("GLYPHS_MCP_COLOR"))
        RESET = "\x1b[0m" if use_color else ""
        BOLD = "\x1b[1m" if use_color else ""
        GREEN = "\x1b[32m" if use_color else ""
        RED = "\x1b[31m" if use_color else ""
        DIM = "\x1b[2m" if use_color else ""
        OK = "✓"
        BAD = "✗"

        def h(title: str) -> None:
            print("\n" + line)
            print("{}{}{}".format(BOLD, title.center(width), RESET))
            print(line)

        def print_kv(label: str, value: str) -> None:
            print("{:>18}: {}".format(label, value))

        # Header
        h("Glyphs MCP Plugin Diagnostics")
        print_kv("Python exec", _resolve_python_executable())
        print_kv("Python version", sys.version.splitlines()[0])

        # Show vendor status
        if _vendor_path:
            print_kv("Vendor path", f"{GREEN}{OK} {_vendor_path}{RESET}")
        else:
            print_kv("Vendor path", f"{RED}{BAD} not found (dependencies missing){RESET}")

        print("\n" + line)
        print("Diagnostics complete. Start the server from the menu to proceed.")
        print(line)
    except Exception as e:  # pragma: no cover - diagnostics must not fail
        print("Diagnostics error:", e)


# Monkey-patch the plugin menu action to run diagnostics before server launch
if hasattr(MCPBridgePlugin, "StartStopServer_"):
    _orig_StartStopServer_ = MCPBridgePlugin.StartStopServer_

    def _patched_StartStopServer_(self, sender):  # type: ignore[override]
        # Run diagnostics only once per plugin instance to reduce noise
        if not getattr(self, "_diagnostics_done", False):
            run_diagnostics()
            setattr(self, "_diagnostics_done", True)
        return _orig_StartStopServer_(self, sender)

    MCPBridgePlugin.StartStopServer_ = _patched_StartStopServer_  # type: ignore[assignment]
