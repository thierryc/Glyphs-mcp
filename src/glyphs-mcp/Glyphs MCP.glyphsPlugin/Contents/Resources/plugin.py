# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import os
import site
import sys
import traceback
from pathlib import Path
from typing import List, Optional, Tuple


def _glyphs_major_version() -> str:
    """Best-effort Glyphs major version detection for app support paths."""
    override = os.environ.get("GLYPHS_MCP_GLYPHS_VERSION", "").strip()
    if override in {"3", "4"}:
        return override

    try:
        from Foundation import NSBundle  # type: ignore[import-not-found]

        bundle = NSBundle.mainBundle()
        values = [
            bundle.bundleIdentifier() or "",
            bundle.objectForInfoDictionaryKey_("CFBundleName") or "",
            bundle.objectForInfoDictionaryKey_("CFBundleExecutable") or "",
        ]
        haystack = " ".join(str(value) for value in values).lower()
        if "glyphs4" in haystack or "glyphs 4" in haystack:
            return "4"
        if "glyphs3" in haystack or "glyphs 3" in haystack:
            return "3"
    except Exception:
        pass

    try:
        exe = Path(sys.executable).resolve()
        names = [exe.name] + [parent.name for parent in exe.parents]
        haystack = " ".join(names).lower()
        if "glyphs 4" in haystack or "glyphs4" in haystack:
            return "4"
        if "glyphs 3" in haystack or "glyphs3" in haystack:
            return "3"
    except Exception:
        pass

    return "3"


def _glyphs_user_site_packages() -> Path:
    """Return the user-writable site-packages used by Glyphs scripts.

    This is typically "~/Library/Application Support/Glyphs N/Scripts/site-packages".
    """
    base = Path.home() / "Library" / "Application Support" / ("Glyphs " + _glyphs_major_version())
    return base / "Scripts" / "site-packages"


def _ensure_user_site_packages_on_path() -> None:
    """Ensure the active Python can import MCP dependencies.

    Glyphs may run either its embedded runtime or an external python.org/Homebrew
    interpreter. Always add the Glyphs Scripts/site-packages directory, and when
    Glyphs is using an external Python also add that interpreter's user site so
    pip installs land where the plug-in can see them.
    """

    def _add(path: Optional[Path]) -> None:
        if not path:
            return
        try:
            real = path.resolve()
        except Exception:
            real = path
        if not real.is_dir():
            return

        # Remove any existing entries that point to the same directory so we
        # can control ordering (especially when mixing Glyphs' Python with
        # an external interpreter).
        try:
            real_resolved = real.resolve()
        except Exception:
            real_resolved = real
        real_str = str(real)
        real_resolved_str = str(real_resolved)

        for entry in list(sys.path):
            try:
                entry_path = Path(entry)
            except Exception:
                entry_path = None

            if entry == real_str or entry == real_resolved_str:
                sys.path.remove(entry)
                continue

            if entry_path is not None:
                try:
                    if entry_path.resolve() == real_resolved:
                        sys.path.remove(entry)
                except Exception:
                    continue

        try:
            site.addsitedir(str(real))
        except Exception:
            # Never block plugin startup on sys.path tweaks
            pass

    glyphs_site = _glyphs_user_site_packages()

    # Detect whether Glyphs is running with its embedded Python.
    exe = Path(sys.executable).resolve()
    is_embedded = any(parent.name.endswith(".app") and "Glyphs" in parent.name for parent in exe.parents)

    additions: List[Path] = []

    if not is_embedded:
        try:
            import site as _site  # shadowing module name is intentional

            user_site = Path(_site.getusersitepackages())
        except Exception:
            user_site = None
        else:
            # Avoid re-adding the Glyphs Scripts folder when Glyphs delegates to it.
            if user_site:
                try:
                    if glyphs_site and user_site.resolve() == glyphs_site.resolve():
                        pass
                    else:
                        additions.append(user_site)
                except Exception:
                    additions.append(user_site)

    # Always add Glyphs' Scripts/site-packages last so external site-packages
    # take precedence when both are present.
    additions.append(glyphs_site)

    for entry in additions:
        _add(entry)

    # Allow manual overrides for debugging (colon-separated list).
    extras = os.environ.get("GLYPHS_MCP_EXTRA_SITEPACKAGES", "")
    for entry in (p.strip() for p in extras.split(os.pathsep) if p.strip()):
        _add(Path(os.path.expanduser(entry)))


_ensure_user_site_packages_on_path()


def _maybe_prefer_vendored_site_packages() -> None:
    """Prefer bundled ABI-matched deps when the plug-in ships with a vendor tree."""
    try:
        import platform

        py_tag = "py{}{}".format(sys.version_info.major, sys.version_info.minor)
        machine = (platform.machine() or "").lower()
        if machine == "aarch64":
            machine = "arm64"
        vendor_root = Path(__file__).resolve().parent / "vendor"
        candidate = vendor_root / "{}-{}".format(py_tag, machine) / "site-packages"
        if not candidate.is_dir():
            return
        cand = str(candidate)
        sys.path[:] = [p for p in sys.path if p != cand]
        sys.path.insert(0, cand)
    except Exception:
        pass


_maybe_prefer_vendored_site_packages()

# Import utility functions and apply fixes
from utils import fix_glyphs_console
import importlib
fix_glyphs_console()


def _console_log(message: str) -> None:
    """Log to the Glyphs macro console and, when available, macOS Console."""
    try:
        print(message)
    except Exception:
        pass

    try:
        from Foundation import NSLog  # type: ignore[import-not-found]

        NSLog(message)
    except Exception:
        pass


def _debug_startup_environment() -> None:
    """Print import diagnostics before loading Glyphs MCP tool modules."""
    try:
        _console_log("[Glyphs MCP] startup debug")
        _console_log("[Glyphs MCP] sys.executable: {}".format(sys.executable))
        _console_log("[Glyphs MCP] sys.version: {}".format(sys.version.replace("\n", " ")))
        _console_log("[Glyphs MCP] sys.prefix: {}".format(sys.prefix))
        _console_log("[Glyphs MCP] sys.base_prefix: {}".format(getattr(sys, "base_prefix", "")))
        _console_log("[Glyphs MCP] Glyphs major: {}".format(_glyphs_major_version()))
        _console_log("[Glyphs MCP] Glyphs site-packages: {}".format(_glyphs_user_site_packages()))
        try:
            _console_log("[Glyphs MCP] Python user site: {}".format(site.getusersitepackages()))
        except Exception as exc:
            _console_log("[Glyphs MCP] Python user site unavailable: {}".format(repr(exc)))

        _console_log("[Glyphs MCP] sys.path:")
        for entry in sys.path:
            _console_log("[Glyphs MCP]   {}".format(entry))

        for name in ("objc", "Foundation", "AppKit", "GlyphsApp"):
            try:
                module = __import__(name)
                _console_log("[Glyphs MCP] import {} OK: {}".format(name, getattr(module, "__file__", "<built-in>")))
            except Exception as exc:
                _console_log("[Glyphs MCP] import {} FAILED: {}".format(name, repr(exc)))
                try:
                    traceback.print_exc()
                except Exception:
                    pass
    except Exception:
        try:
            traceback.print_exc()
        except Exception:
            pass


STARTUP_IMPORT_ERROR = None

_debug_startup_environment()

try:
    # Import MCP tools (this registers all the tools)
    from mcp_tools import mcp

    # Import code execution tools (this registers the execution tools)
    import code_execution

    # Import bundled documentation resources so they are registered with FastMCP
    import documentation_resources  # noqa: F401
    # Import the guide resource so it is registered
    import guide_resources  # noqa: F401
    # Import prompt examples so they are registered
    import prompt_examples  # noqa: F401
    # Import docs helper tools (search/fetch) so they are registered
    import docs_tools  # noqa: F401
    # Import kerning dataset resources so they are registered
    import kerning_resources  # noqa: F401

    # Import and initialize the plugin
    from glyphs_plugin import MCPBridgePlugin
except Exception as exc:  # pragma: no cover - requires broken local environment
    STARTUP_IMPORT_ERROR = exc
    try:
        traceback.print_exc()
    except Exception:
        pass

    try:
        from GlyphsApp import Message  # type: ignore[import-not-found]
        from GlyphsApp.plugins import GeneralPlugin  # type: ignore[import-not-found]
    except Exception:
        Message = None
        GeneralPlugin = object

    def _startup_error_message() -> str:
        err = repr(STARTUP_IMPORT_ERROR)
        return (
            "Glyphs MCP could not load its Python dependencies.\n\n"
            "{}\n\n"
            "Re-run the installer to refresh the runtime packages. "
            "If you recently changed Glyphs Python versions, remove the old "
            "packages from the active ~/Library/Application Support/Glyphs N/Scripts/site-packages "
            "before reinstalling."
        ).format(err)

    class MCPBridgePlugin(GeneralPlugin):  # type: ignore[misc]
        def settings(self):
            try:
                self.name = "Glyphs MCP"
            except Exception:
                pass

        def start(self):
            try:
                print("[Glyphs MCP] Startup failed: {}".format(STARTUP_IMPORT_ERROR))
            except Exception:
                pass

            if Message:
                try:
                    Message("Glyphs MCP failed to load", _startup_error_message(), "OK")
                except Exception:
                    pass


# ------------------------------------------------------------
# Diagnostics executed before launching the MCP server
# ------------------------------------------------------------
def _get_site_packages_dir() -> str:
    """Return the Scripts/site-packages directory used for dependencies."""
    return str(_glyphs_user_site_packages())


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
            "mcp",
            "fastmcp",
            "starlette",
            "uvicorn",
            "httpx",
            "sse_starlette",
            "typing_extensions",
            "objc",
            "Foundation",
            "AppKit",
        ]
        # Also useful in the Glyphs environment
        optional: List[str] = ["GlyphsApp", "httpx_sse"]

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
        print("Diagnostics complete. Click Start in the status window to proceed.")
        print(line)
    except Exception as e:  # pragma: no cover - diagnostics must not fail
        print("Diagnostics error:", e)


# Monkey-patch the plugin start action to run diagnostics before server launch
if hasattr(MCPBridgePlugin, "StartServer_"):
    _orig_StartServer_ = MCPBridgePlugin.StartServer_

    def _patched_StartServer_(self, sender):  # type: ignore[override]
        # Run diagnostics only once per plugin instance to reduce noise
        if not getattr(self, "_diagnostics_done", False):
            run_diagnostics()
            setattr(self, "_diagnostics_done", True)
        return _orig_StartServer_(self, sender)

    MCPBridgePlugin.StartServer_ = _patched_StartServer_  # type: ignore[assignment]
