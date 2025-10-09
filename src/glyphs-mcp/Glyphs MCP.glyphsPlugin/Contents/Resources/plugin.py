# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import os
import site
import sys
from pathlib import Path


def _glyphs_user_site_packages() -> str:
    """Return the user-writable site-packages used by Glyphs scripts.

    This is typically "~/Library/Application Support/Glyphs 3/Scripts/site-packages".
    """
    base = os.path.expanduser(os.path.join("~", "Library", "Application Support", "Glyphs 3"))
    return os.path.join(base, "Scripts", "site-packages")


def _ensure_user_site_packages_on_path() -> None:
    """Add Glyphs Scripts/site-packages to sys.path if present.

    This replaces the previous behavior of loading vendored dependencies from the
    plug-in bundle. Dependencies are now installed outside the bundle into the
    user-writable Scripts/site-packages directory.
    """
    user_site = _glyphs_user_site_packages()
    try:
        if os.path.isdir(user_site) and user_site not in sys.path:
            site.addsitedir(user_site)
    except Exception:
        # Never block plugin startup on sys.path tweaks
        pass


_ensure_user_site_packages_on_path()

# Import utility functions and apply fixes
from utils import fix_glyphs_console
import importlib
from typing import List, Tuple
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
def _get_site_packages_dir() -> str:
    """Return the Scripts/site-packages directory used for dependencies."""
    return _glyphs_user_site_packages()


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

        site_dir = _get_site_packages_dir()
        print_kv("User site-packages", site_dir)
        print_kv("On sys.path", str(site_dir in sys.path))

        # Minimal set required to run the local MCP HTTP server
        required: List[str] = [
            "fastmcp",
            "starlette",
            "uvicorn",
            "httpx",
            "sse_starlette",
            "typing_extensions",
        ]
        # Also useful in the Glyphs environment
        optional: List[str] = ["GlyphsApp", "objc", "AppKit", "httpx_sse"]

        # Required deps table
        h("Required Dependencies")
        req_results = [_check_dependency(name) for name in required]
        name_width = max(12, max(len(n) for n, _, _ in req_results))
        ok_count = sum(1 for _, ok, _ in req_results if ok)
        miss_count = len(req_results) - ok_count
        for name, ok, details in req_results:
            status = f"{GREEN}{OK} OK{RESET}" if ok else f"{RED}{BAD} MISSING{RESET}"
            print("  {name:<{w}}  {status}  {dim}{details}{reset}".format(
                name=name, w=name_width, status=status, dim=DIM if ok else "", details=details if ok else details, reset=RESET
            ))
        print("-- Summary: {}{} OK{}, {}{} missing{}".format(
            GREEN if use_color else "", ok_count, RESET if use_color else "",
            RED if use_color else "", miss_count, RESET if use_color else "",
        ))

        # Optional deps table
        h("Optional Dependencies")
        opt_results = [_check_dependency(name) for name in optional]
        name_width_opt = max(12, max(len(n) for n, _, _ in opt_results))
        for name, ok, details in opt_results:
            status = f"{OK} available" if ok else "- not present"
            color = GREEN if ok and use_color else DIM if use_color else ""
            print("  {name:<{w}}  {color}{status}{reset}{det}".format(
                name=name, w=name_width_opt, color=color, status=status, reset=RESET if use_color else "", det=("  " + DIM + details + RESET) if ok and use_color else ("  " + details if ok else "")
            ))

        # Where fastmcp is loaded from
        try:
            import fastmcp  # type: ignore

            h("Package Locations")
            print_kv("fastmcp", getattr(fastmcp, "__file__", "?"))
        except Exception:
            pass

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
