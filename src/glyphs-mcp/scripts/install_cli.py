#!/usr/bin/env python3
"""
Installer for the Glyphs MCP plug-in.

- Interactive by default when run without installer flags.
- Supports an explicit non-interactive mode for scripted installs.
- Lets the user choose between Glyphs' bundled Python or a custom Python.
- Installs Python dependencies accordingly.
- Copies or links the plug-in bundle into the Glyphs Plugins folder.

Run:
  python3 install.py
  python src/glyphs-mcp/scripts/install_cli.py --non-interactive ...
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import FrozenSet, List, Literal, Optional, Tuple

try:
    from rich import box
    from rich.console import Console
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
except Exception:  # fallback if rich isn't available in the runner's Python
    print(
        "The installer prefers the 'rich' package for a nicer UI.\n"
        "You can install it with: python3 -m pip install --user rich\n"
        "Continuing with a plain console UI…"
    )

    class _Dummy:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, name):
            def f(*a, **k):
                return self
            return f

        def __call__(self, *a, **k):
            return self

        def __str__(self):
            return ""

    class _PlainConsole:
        def print(self, *a, **k):  # ignore styling kwargs
            if a:
                # Drop any rich Text/Panel-like objects
                try:
                    msg = " ".join(str(x) for x in a)
                except Exception:
                    msg = ""
                print(msg)
            else:
                print()

        def log(self, *a, **k):
            self.print(*a, **k)

        def rule(self, title="", *a, **k):
            line = "-" * 10
            if title:
                print(f"{line} {title} {line}")
            else:
                print(line * 4)

    class _Prompt:
        @staticmethod
        def ask(prompt, choices=None, default=None):
            try:
                val = input(f"{prompt} ").strip()
            except EOFError:
                val = ""
            if not val:
                return default if default is not None else (choices[0] if choices else "")
            if choices and val not in choices:
                return default if default is not None else choices[0]
            return val

    class _Confirm:
        @staticmethod
        def ask(prompt, default=False):
            yn = "Y/n" if default else "y/N"
            try:
                val = input(f"{prompt} [{yn}] ").strip().lower()
            except EOFError:
                val = ""
            if not val:
                return default
            return val in ("y", "yes", "true", "1")

    class _Box:
        SIMPLE_HEAVY = object()
        SIMPLE = object()
        MINIMAL_HEAVY_HEAD = object()

    class _PlainTable:
        def __init__(self, box=None):
            self._columns = []
            self._rows = []

        def add_column(self, name):
            self._columns.append(str(name))

        def add_row(self, *cells):
            self._rows.append([str(c) for c in cells])

        def __str__(self):
            widths = [len(h) for h in self._columns]
            for row in self._rows:
                for i, cell in enumerate(row):
                    if i < len(widths):
                        widths[i] = max(widths[i], len(cell))
                    else:
                        widths.append(len(cell))
            def fmt_row(cells):
                return " | ".join((cells[i] if i < len(cells) else "").ljust(widths[i]) for i in range(len(widths)))
            lines = []
            if self._columns:
                lines.append(fmt_row(self._columns))
                lines.append("-+-".join("-" * w for w in widths))
            for r in self._rows:
                lines.append(fmt_row(r))
            return "\n".join(lines)

    class _Panel:
        def __init__(self, content, title=None, border_style=None):
            self.content = content
            self.title = title

        @staticmethod
        def fit(content, title=None, border_style=None):
            return _Panel(content, title=title, border_style=border_style)

        def __str__(self):
            title = f"[{self.title}]\n" if self.title else ""
            return f"{title}{self.content}"

    class _Text:
        def __init__(self, text):
            self.text = str(text)

        def __str__(self):
            return self.text

    # Map rich-like symbols to simple shims
    Console = _PlainConsole
    Prompt = _Prompt
    Confirm = _Confirm
    Table = _PlainTable
    Panel = _Panel
    Text = _Text
    box = _Box()


console = Console()

PYTHON_BINARY_PATTERN = re.compile(r"^python3(\.\d+)?$")
MIN_PY_VERSION = (3, 11, 0)  # Allow 3.11+, prefer 3.14+
MAX_PY_VERSION_EXCLUSIVE = (3, 15, 0)  # Disallow 3.15+ until tested
SKILL_PREFIX = "glyphs-mcp-"
MANAGED_SKILL_NAMES = (
    "glyphs-mcp-connect",
    "glyphs-mcp-features",
    "glyphs-mcp-italic-first-pass",
    "glyphs-mcp-kerning",
    "glyphs-mcp-outlines-docs",
    "glyphs-mcp-spacing",
)
MCP_ENDPOINT = "http://127.0.0.1:9680/mcp/"
CODEX_SERVER_NAME = "glyphs-mcp-server"
CLAUDE_DESKTOP_SERVER_NAME = "glyphs-mcp-server"
CLAUDE_CODE_SERVER_NAME = "glyphs-mcp"
UNINSTALL_COMPONENTS = frozenset({"plugin", "skills", "clients"})
REQUIRED_RUNTIME_MODULES = [
    "mcp",
    "fastmcp",
    "pydantic_core",
    "starlette",
    "uvicorn",
    "httpx",
    "sse_starlette",
    "typing_extensions",
    "pkg_resources",
    "fontParts",
    "fontTools",
    "objc",
    "Foundation",
    "AppKit",
]


def plugin_executable_path(bundle: Path) -> Path:
    return bundle / "Contents" / "MacOS" / "plugin"


def sign_plugin_executable(bundle: Path) -> None:
    """Ad-hoc sign the native Glyphs plug-in loader for local installs."""
    executable = plugin_executable_path(bundle)
    if not executable.exists():
        console.print(f"[yellow]Plugin executable not found, skipping signing:[/yellow] {executable}")
        return

    console.print(f"[cyan]Ad-hoc signing plug-in executable:[/cyan] {executable}")
    try:
        subprocess.run(
            ["/usr/bin/codesign", "--force", "--sign", "-", str(executable)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["/usr/bin/codesign", "--verify", "--verbose=2", str(executable)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        console.print("[yellow]codesign not found; skipping plug-in executable signing.[/yellow]")
    except subprocess.CalledProcessError as e:
        details = (e.stderr or e.stdout or str(e)).strip()
        console.print(f"[red]Failed to sign plug-in executable:[/red] {details}")
        raise SystemExit(2)


@dataclass
class InstallerOptions:
    non_interactive: bool
    glyphs_version: Literal["3", "4", "both"] = "4"
    skip_deps: bool = False
    python_mode: Optional[Literal["glyphs", "custom"]] = None
    python_path: Optional[Path] = None
    plugin_mode: Optional[Literal["copy", "link"]] = None
    install_skills: Optional[bool] = None
    skills_target: Optional[Literal["codex", "claude", "both"]] = None
    overwrite_plugin: Optional[bool] = None
    overwrite_skills: Optional[bool] = None
    show_client_guidance: Optional[bool] = None
    uninstall: bool = False
    uninstall_components: FrozenSet[str] = field(default_factory=frozenset)
    dry_run: bool = False
    confirm_uninstall: bool = False


@dataclass(frozen=True)
class UninstallCandidate:
    identifier: str
    component: Literal["plugin", "skills", "clients"]
    label: str
    location: Path
    state: Literal["removable", "missing", "preserved", "blocked"]
    detail: str
    glyphs_version: Optional[Literal["3", "4"]] = None
    client_kind: Optional[Literal["codex", "claude-desktop", "claude-code"]] = None


@dataclass(frozen=True)
class GlyphsUninstallPlan:
    components: FrozenSet[str]
    candidates: Tuple[UninstallCandidate, ...]

    @property
    def removable_candidates(self) -> Tuple[UninstallCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.state == "removable")


@dataclass(frozen=True)
class UninstallOutcome:
    candidate: UninstallCandidate
    status: Literal["removed", "skipped", "failed"]
    message: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def glyphs_base_dir(glyphs_version: Literal["3", "4"] = "4") -> Path:
    return Path.home() / "Library" / "Application Support" / f"Glyphs {glyphs_version}"


def glyphs_plugins_dir(glyphs_version: Literal["3", "4"] = "4") -> Path:
    return glyphs_base_dir(glyphs_version) / "Plugins"


def glyphs_scripts_site_packages(glyphs_version: Literal["3", "4"] = "4") -> Path:
    return glyphs_base_dir(glyphs_version) / "Scripts" / "site-packages"


def codex_skills_dir() -> Path:
    return Path.home() / ".codex" / "skills"


def claude_code_skills_dir() -> Path:
    return Path.home() / ".claude" / "skills"


def codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def claude_desktop_config_path() -> Path:
    return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def claude_code_config_path() -> Path:
    return Path.home() / ".claude.json"


def glyphs_python_pip(glyphs_version: Literal["3", "4"] = "4") -> Optional[Path]:
    base = glyphs_base_dir(glyphs_version) / "Repositories" / "GlyphsPythonPlugin" / "Python.framework"
    pip = base / "Versions" / "Current" / "bin" / "pip3"
    return pip if pip.exists() else None


def glyphs_preferences_domain(glyphs_version: Literal["3", "4"] = "4") -> str:
    return "com.GeorgSeifert.Glyphs4" if glyphs_version == "4" else "com.GeorgSeifert.Glyphs3"


def glyphs_selected_python_framework(glyphs_version: Literal["3", "4"] = "4") -> Optional[Path]:
    try:
        out = subprocess.check_output(
            ["defaults", "read", glyphs_preferences_domain(glyphs_version), "GSPythonFrameworkPath"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None
    if not out:
        return None
    framework = Path(out).expanduser()
    return framework if framework.exists() else None


def glyphs_selected_python_bin(glyphs_version: Literal["3", "4"] = "4") -> Optional[Path]:
    framework = glyphs_selected_python_framework(glyphs_version)
    if not framework:
        return None
    py = framework / "bin" / "python3"
    if py.exists():
        return py
    # python.org framework installs often expose only python3.X.
    candidates = sorted((framework / "bin").glob("python3.*")) if (framework / "bin").is_dir() else []
    for candidate in candidates:
        if candidate.name.endswith("-config"):
            continue
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def glyphs_python_bin(glyphs_version: Literal["3", "4"] = "4") -> Optional[Path]:
    pip = glyphs_python_pip(glyphs_version)
    if not pip:
        return None
    py = Path(pip).parent / "python3"
    return py if py.exists() else None


def version_tuple(version_str: str) -> Tuple[int, int, int]:
    parts = version_str.strip().split(".")
    out = []
    for p in parts[:3]:
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)  # type: ignore[return-value]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install Glyphs MCP interactively or via an explicit non-interactive CLI.",
        add_help=True,
    )
    parser.add_argument("--non-interactive", action="store_true", help="Run without prompts. Required choices must be provided explicitly.")
    parser.add_argument("--glyphs-version", choices=["3", "4", "both"], default="4", help="Glyphs major version to target. 'both' is available only with --uninstall.")
    parser.add_argument("--uninstall", action="store_true", help="Review and remove safely attributable Glyphs MCP components.")
    parser.add_argument(
        "--uninstall-component",
        action="append",
        choices=sorted(UNINSTALL_COMPONENTS),
        default=[],
        help="Limit uninstall to a component category. Repeat for multiple categories.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview an uninstall without changing files.")
    parser.add_argument("--confirm-uninstall", action="store_true", help="Required confirmation for a non-interactive uninstall.")
    parser.add_argument("--skip-deps", action="store_true", help="Skip Python dependency installation. Useful for dev-mode plug-in symlink tests.")
    parser.add_argument("--python-mode", choices=["glyphs", "custom"], help="Python environment to use for dependency installation.")
    parser.add_argument("--python-path", help="Absolute path to python3 when using --python-mode custom.")
    parser.add_argument("--plugin-mode", choices=["copy", "link"], help="How to install the Glyphs plug-in bundle.")

    skills_group = parser.add_mutually_exclusive_group()
    skills_group.add_argument("--install-skills", action="store_true", help="Install the managed Glyphs MCP skill bundle.")
    skills_group.add_argument("--skip-skills", action="store_true", help="Skip skill bundle installation.")
    parser.add_argument("--skills-target", choices=["codex", "claude", "both"], help="Where to install the managed skills when --install-skills is set.")

    plugin_overwrite = parser.add_mutually_exclusive_group()
    plugin_overwrite.add_argument("--overwrite-plugin", action="store_true", help="Replace an existing installed plug-in.")
    plugin_overwrite.add_argument("--keep-plugin", action="store_true", help="Keep an existing installed plug-in unchanged.")

    skills_overwrite = parser.add_mutually_exclusive_group()
    skills_overwrite.add_argument("--overwrite-skills", action="store_true", help="Replace existing managed Glyphs MCP skills.")
    skills_overwrite.add_argument("--keep-skills", action="store_true", help="Keep existing managed Glyphs MCP skills unchanged.")

    guidance_group = parser.add_mutually_exclusive_group()
    guidance_group.add_argument("--show-client-guidance", action="store_true", help="Print MCP client setup guidance after installation.")
    guidance_group.add_argument("--skip-client-guidance", action="store_true", help="Do not print MCP client setup guidance.")

    return parser


def parse_cli_options(argv: Optional[List[str]] = None) -> InstallerOptions:
    parser = build_arg_parser()
    ns = parser.parse_args(argv)

    python_path = Path(ns.python_path).expanduser().resolve() if ns.python_path else None
    install_skills: Optional[bool]
    if ns.install_skills:
        install_skills = True
    elif ns.skip_skills:
        install_skills = False
    else:
        install_skills = None

    overwrite_plugin = True if ns.overwrite_plugin else False if ns.keep_plugin else None
    overwrite_skills = True if ns.overwrite_skills else False if ns.keep_skills else None
    show_client_guidance = True if ns.show_client_guidance else False if ns.skip_client_guidance else None

    options = InstallerOptions(
        non_interactive=ns.non_interactive,
        glyphs_version=ns.glyphs_version,
        skip_deps=ns.skip_deps,
        python_mode=ns.python_mode,
        python_path=python_path,
        plugin_mode=ns.plugin_mode,
        install_skills=install_skills,
        skills_target=ns.skills_target,
        overwrite_plugin=overwrite_plugin,
        overwrite_skills=overwrite_skills,
        show_client_guidance=show_client_guidance,
        uninstall=ns.uninstall,
        uninstall_components=frozenset(ns.uninstall_component),
        dry_run=ns.dry_run,
        confirm_uninstall=ns.confirm_uninstall,
    )
    validate_options(options, parser)
    return options


def validate_options(options: InstallerOptions, parser: argparse.ArgumentParser) -> None:
    if options.uninstall:
        install_only_options = [
            options.skip_deps,
            options.python_mode is not None,
            options.python_path is not None,
            options.plugin_mode is not None,
            options.install_skills is not None,
            options.skills_target is not None,
            options.overwrite_plugin is not None,
            options.overwrite_skills is not None,
            options.show_client_guidance is not None,
        ]
        if any(install_only_options):
            parser.error("Install-only options cannot be used with --uninstall.")
        if options.non_interactive and not options.dry_run and not options.confirm_uninstall:
            parser.error("--non-interactive --uninstall requires --confirm-uninstall (or use --dry-run).")
        return

    if options.glyphs_version == "both":
        parser.error("--glyphs-version both can only be used with --uninstall.")
    if options.uninstall_components:
        parser.error("--uninstall-component can only be used with --uninstall.")
    if options.dry_run:
        parser.error("--dry-run can only be used with --uninstall.")
    if options.confirm_uninstall:
        parser.error("--confirm-uninstall can only be used with --uninstall.")

    if options.skip_deps:
        if options.python_mode is not None:
            parser.error("--python-mode cannot be used with --skip-deps.")
        if options.python_path is not None:
            parser.error("--python-path cannot be used with --skip-deps.")

    if options.python_mode == "custom" and options.python_path is None:
        parser.error("--python-path is required when --python-mode custom is used.")

    if options.python_path is not None and not options.python_path.exists():
        parser.error(f"--python-path does not exist: {options.python_path}")

    if options.install_skills is False:
        if options.skills_target is not None:
            parser.error("--skills-target cannot be used with --skip-skills.")
        if options.overwrite_skills is not None:
            parser.error("--overwrite-skills/--keep-skills cannot be used with --skip-skills.")

    if options.non_interactive:
        missing: List[str] = []
        if not options.skip_deps and options.python_mode is None:
            missing.append("--python-mode")
        if options.plugin_mode is None:
            missing.append("--plugin-mode")
        if missing:
            parser.error(f"--non-interactive requires {' and '.join(missing)}.")

        if options.install_skills is None:
            parser.error("--non-interactive requires one of --install-skills or --skip-skills.")

        if options.install_skills and options.skills_target is None:
            parser.error("--install-skills requires --skills-target in non-interactive mode.")


def format_missing_policy_error(subject: str, positive_flag: str, negative_flag: str) -> str:
    return f"Existing {subject} found. Re-run with {positive_flag} or {negative_flag}."


def python_version(py: Path) -> Optional[str]:
    try:
        out = subprocess.check_output([str(py), "-c", "import sys; print(sys.version.split()[0])"], text=True)
        return out.strip()
    except Exception:
        return None


@dataclass
class PythonCandidate:
    path: Path
    version: Optional[str]
    source: str  # python.org / homebrew / system / path

    @property
    def version_key(self) -> Tuple[int, int, int]:
        return version_tuple(self.version or "0.0.0")


def _sort_python_candidates(cands: List[PythonCandidate]) -> None:
    # Sort best-first: highest version, prefer >= 3.12 and python.org builds.
    #
    # Note: reverse=True means `True` sorts before `False`, so use
    # `c.source == "python.org"` as a tie-break.
    cands.sort(key=lambda c: (c.version_key, c.source == "python.org"), reverse=True)


def detect_python_candidates() -> List[PythonCandidate]:
    cands: List[PythonCandidate] = []
    seen: set[Path] = set()

    def add_candidate(path: Path, source: str) -> None:
        if not path.exists():
            return
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        if resolved in seen:
            return
        ver = python_version(resolved)
        if not ver:
            return
        vt = version_tuple(ver)
        if vt < MIN_PY_VERSION:
            return
        if vt >= MAX_PY_VERSION_EXCLUSIVE:
            return
        cands.append(PythonCandidate(path, ver, source))
        seen.add(resolved)

    def iter_python_bins(bin_dir: Path) -> List[Path]:
        paths: List[Path] = []
        if not bin_dir.is_dir():
            return paths
        try:
            entries = sorted(bin_dir.iterdir())
        except Exception:
            return paths
        for candidate in entries:
            try:
                if not candidate.is_file():
                    continue
            except OSError:
                # Ignore unreadable entries such as protected system binaries.
                continue
            try:
                if not os.access(candidate, os.X_OK):
                    continue
            except OSError:
                continue
            if PYTHON_BINARY_PATTERN.match(candidate.name):
                paths.append(candidate)
        return paths

    # Explicit python.org "Current" convenience path (user request) and python.org installs
    current_bin = Path("/Library/Frameworks/Python.framework/Versions/Current/bin")
    for python_bin in iter_python_bins(current_bin):
        add_candidate(python_bin, "python.org")

    framework = Path("/Library/Frameworks/Python.framework/Versions")
    if framework.exists():
        for vdir in sorted(framework.iterdir()):
            if not vdir.is_dir() or vdir.name == "Current":
                continue
            for python_bin in iter_python_bins(vdir / "bin"):
                add_candidate(python_bin, "python.org")

    # Homebrew installations (arm64 + Intel prefixes)
    for brew_prefix in (Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
        for python_bin in iter_python_bins(brew_prefix):
            add_candidate(python_bin, "homebrew")

    # Common system directories
    for sys_prefix in (Path("/usr/bin"), Path("/bin")):
        for python_bin in iter_python_bins(sys_prefix):
            add_candidate(python_bin, "system")

    # PATH discovery (last, to avoid duping brew/python.org entries)
    for path_dir in (Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p):
        source = "homebrew" if "homebrew" in str(path_dir) else "system" if str(path_dir).startswith("/usr") else "path"
        for python_bin in iter_python_bins(path_dir):
            add_candidate(python_bin, source)

    # System Python fallback (in case PATH discovery skipped it)
    add_candidate(Path("/usr/bin/python3"), "system")

    _sort_python_candidates(cands)
    return cands


def verify_runtime(python: Path, extra_site_packages: Optional[Path] = None) -> bool:
    """Verify required packages import cleanly in the selected Python.

    Returns True on success, False otherwise, and prints guidance.
    """
    console.print(Panel.fit(f"Verifying runtime imports in: {python}", title="Verify", border_style="white"))
    code = (
        "import sys;\n"
        "import site;\n"
        f"extra_site={str(extra_site_packages)!r};\n"
        "if extra_site:\n"
        "  site.addsitedir(extra_site)\n"
        f"mods={REQUIRED_RUNTIME_MODULES!r};\n"
        "missing=[];\n"
        "import importlib;\n"
        "\n"
        "for m in mods:\n"
        "  try:\n"
        "    importlib.import_module(m)\n"
        "  except Exception as e:\n"
        "    missing.append((m,str(e)))\n"
        "\n"
        "# Sanity checks for common version-mismatch issues.\n"
        "try:\n"
        "  import mcp.types as _t\n"
        "  if not hasattr(_t, 'AnyFunction'):\n"
        "    missing.append(('mcp.types.AnyFunction', 'missing (upgrade mcp)'))\n"
        "except Exception as e:\n"
        "  missing.append(('mcp.types', str(e)))\n"
        "\n"
        "print('Python:', sys.executable);\n"
        "print('Version:', sys.version.split()[0]);\n"
        "print('OK' if not missing else 'MISSING:'+str(missing))\n"
    )
    try:
        out = subprocess.check_output([str(python), "-c", code], text=True)
        console.print(Text(out))
        if "MISSING:" in out:
            console.print(
                "[red]Some packages failed to import.\n"
                "Try reinstalling with --no-cache-dir and force-reinstall:[/red]\n"
                f"  {python} -m pip install --user --no-cache-dir --force-reinstall -r {repo_root()/ 'requirements.txt'}\n"
                "If objc, Foundation, or AppKit are missing, PyObjC did not install into the Python selected in Glyphs. "
                "Install the Glyphs Python module or run pip for the exact Python shown above."
            )
            return False
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Verification failed to run:[/red] {e}")
        return False


def run(cmd: List[str]) -> None:
    console.log(f"[dim]$ {' '.join(cmd)}[/dim]")
    subprocess.check_call(cmd)


def install_with_glyphs_python(requirements: Path, glyphs_version: Literal["3", "4"] = "4") -> None:
    selected_python = glyphs_selected_python_bin(glyphs_version)
    selected_version = python_version(selected_python) if selected_python else None
    if selected_python and selected_version:
        vt = version_tuple(selected_version)
        if vt < MIN_PY_VERSION or vt >= MAX_PY_VERSION_EXCLUSIVE:
            console.print(f"[red]Glyphs {glyphs_version} is set to unsupported Python {selected_version}. Please use 3.11–3.14.[/red]")
            raise SystemExit(2)
        pip_cmd = [str(selected_python), "-m", "pip"]
        verify_python = selected_python
        source = f"Glyphs {glyphs_version} selected Python {selected_version}"
    else:
        pip = glyphs_python_pip(glyphs_version)
        if not pip:
            console.print("[red]Glyphs Python not found.[/red]")
            console.print(f"Open Glyphs {glyphs_version} → Settings → Addons and install Python (GlyphsPythonPlugin), then re-run.")
            raise SystemExit(2)
        pip_cmd = [str(pip)]
        verify_python = Path(pip).parent / "python3"
        source = f"Glyphs {glyphs_version} bundled Python"

    if not verify_python.exists():
        console.print("[red]Glyphs Python not found.[/red]")
        console.print(f"Open Glyphs {glyphs_version} → Settings → Addons and install Python (GlyphsPythonPlugin), then re-run.")
        raise SystemExit(2)

    target = glyphs_scripts_site_packages(glyphs_version)
    target.mkdir(parents=True, exist_ok=True)
    console.print(Panel.fit(f"{source}\nInstalling requirements into:\n{target}", title="Glyphs Python", border_style="green"))
    run(pip_cmd + ["install", "--upgrade", "pip"])
    run(pip_cmd + [
        "install",
        "--upgrade",
        "--force-reinstall",
        "--no-compile",
        "--only-binary=:all:",
        "--target",
        str(target),
        "-r",
        str(requirements),
    ])

    if not verify_runtime(verify_python, target):
        raise SystemExit(2)


def install_with_custom_python(python: Path, requirements: Path) -> None:
    console.print(Panel.fit(f"Installing requirements to user site for:\n{python}"
                           f"\n(version: {python_version(python) or 'unknown'})",
                           title="Custom Python", border_style="cyan"))
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    run([
        str(python),
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--force-reinstall",
        "--no-compile",
        "--only-binary=:all:",
        "--user",
        "-r",
        str(requirements),
    ])
    if not verify_runtime(python):
        raise SystemExit(2)


def install_plugin(
    mode: str = "copy",
    overwrite_existing: Optional[bool] = None,
    glyphs_version: Literal["3", "4"] = "4",
    sign_executable: bool = True,
) -> bool:
    """Install the plug-in by copying or linking (dev mode)."""
    src = repo_root() / "src" / "glyphs-mcp" / "Glyphs MCP.glyphsPlugin"
    if not src.exists():
        console.print(f"[red]Plugin bundle not found at:[/red] {src}")
        raise SystemExit(2)

    dest_dir = glyphs_plugins_dir(glyphs_version)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    if dest.exists() or dest.is_symlink():
        current = "symlink" if dest.is_symlink() else "folder"
        if overwrite_existing is None:
            overwrite = Confirm.ask(
                f"Plugin already installed as a {current}:\n{dest}\nReplace it?",
                default=True,
            )
        else:
            overwrite = overwrite_existing
        if overwrite:
            try:
                if dest.is_symlink():
                    dest.unlink()
                else:
                    shutil.rmtree(dest)
            except Exception as e:
                console.print(f"[red]Failed to remove existing plugin:[/red] {e}")
                raise SystemExit(2)
        else:
            console.print("[yellow]Keeping existing installation.[/yellow]")
            return False

    if mode == "link":
        console.print(Panel.fit(f"Creating symlink (dev mode) →\n{dest}\n→ {src}", title="Install Plugin", border_style="magenta"))
        os.symlink(src, dest)
    else:
        console.print(Panel.fit(f"Copying plugin →\n{dest}", title="Install Plugin", border_style="magenta"))
        shutil.copytree(src, dest)
    if sign_executable:
        sign_plugin_executable(dest)
    return True


def managed_skill_directories(skills_root: Optional[Path] = None) -> List[Path]:
    root = skills_root or (repo_root() / "skills")
    if not root.is_dir():
        return []

    managed: List[Path] = []
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and entry.name.startswith(SKILL_PREFIX):
            managed.append(entry)
    return managed


def existing_managed_skill_destinations(dest_root: Path, skills_root: Optional[Path] = None) -> List[Path]:
    return [dest_root / src.name for src in managed_skill_directories(skills_root) if (dest_root / src.name).exists() or (dest_root / src.name).is_symlink()]


def _remove_existing_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def _skill_copy_ignore(_src: str, names: List[str]) -> List[str]:
    return [name for name in names if name == ".DS_Store" or name == "__pycache__" or name.endswith(".pyc")]


def install_skill_bundle(
    dest_root: Path,
    skills_root: Optional[Path] = None,
    overwrite_existing: bool = False,
) -> Tuple[List[str], List[str]]:
    skill_dirs = managed_skill_directories(skills_root)
    if not skill_dirs:
        console.print("[red]No managed Glyphs MCP skills were found to install.[/red]")
        raise SystemExit(2)

    dest_root.mkdir(parents=True, exist_ok=True)
    installed: List[str] = []
    skipped: List[str] = []

    for src in skill_dirs:
        dest = dest_root / src.name
        if dest.exists() or dest.is_symlink():
            if not overwrite_existing:
                skipped.append(src.name)
                continue
            _remove_existing_path(dest)
        shutil.copytree(src, dest, ignore=_skill_copy_ignore)
        installed.append(src.name)

    return installed, skipped


def install_skill_bundle_for_targets(
    targets: List[Tuple[str, Path]],
    overwrite_existing: Optional[bool],
    non_interactive: bool,
) -> bool:
    installed_any = False
    source_root = repo_root() / "skills"

    for client_name, dest_root in targets:
        overwrite_for_target = overwrite_existing
        existing = existing_managed_skill_destinations(dest_root, source_root)
        if existing and overwrite_for_target is None:
            if non_interactive:
                raise SystemExit(format_missing_policy_error(
                    f"Glyphs MCP skills in {dest_root}",
                    "--overwrite-skills",
                    "--keep-skills",
                ))
            overwrite_for_target = Confirm.ask(
                f"Glyphs MCP skills already exist in {dest_root}.\nReplace or update the existing managed skills for {client_name}?",
                default=True,
            )

        console.print(
            Panel.fit(
                f"Installing Glyphs MCP skills for {client_name} →\n{dest_root}",
                title="Install Agent Skills",
                border_style="blue",
            )
        )
        installed, skipped = install_skill_bundle(dest_root, source_root, overwrite_existing=bool(overwrite_for_target))
        if installed:
            installed_any = True
            console.print(f"[green]{client_name}:[/green] installed {', '.join(installed)}")
        if skipped:
            console.print(f"[yellow]{client_name}:[/yellow] kept existing {', '.join(skipped)}")

    if installed_any:
        console.print("[cyan]Reload or restart Codex / Claude Code to pick up the newly installed Glyphs MCP skills.[/cyan]")
    return installed_any


def prompt_install_skill_bundle() -> None:
    if not Confirm.ask("Install the Glyphs MCP skill bundle globally for Codex and Claude Code?", default=True):
        return

    selections = [
        ("Codex", codex_skills_dir(), Confirm.ask("Install Glyphs MCP skills into ~/.codex/skills for Codex?", default=True)),
        ("Claude Code", claude_code_skills_dir(), Confirm.ask("Install Glyphs MCP skills into ~/.claude/skills for Claude Code?", default=True)),
    ]
    targets = [(client_name, dest_root) for client_name, dest_root, selected in selections if selected]
    install_skill_bundle_for_targets(targets, overwrite_existing=None, non_interactive=False)


def choose_mode() -> str:
    console.rule("Glyphs MCP Installer")
    console.print("Select your Glyphs App Settings Python environment:")

    # Gather versions and candidates summary for display
    glyphs_py = glyphs_python_bin()
    glyphs_ver = python_version(glyphs_py) if glyphs_py else None
    cands = detect_python_candidates()
    preferred = [c for c in cands if c.version_key >= (3, 12, 0)] or cands
    summary = "none detected"
    if preferred:
        top = preferred[0]
        summary = f"{len(preferred)} detected; highest {top.version or '?'} ({top.source})"

    # Render table with details
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Option")
    table.add_column("Description")
    table.add_column("Details")
    table.add_row("1", "Glyphs' Python (Plugin Manager)", glyphs_ver or "not installed")
    table.add_row("2", "Custom Python (python.org/Homebrew)", summary)
    console.print(table)

    console.print("Note: This must match your selection in Glyphs → Settings → Python.")

    while True:
        choice = Prompt.ask("Enter 1 or 2", choices=["1", "2"], default="1")
        if choice in ("1", "2"):
            return choice


def choose_custom_python(cands: List[PythonCandidate]) -> Path:
    # Filter preferred >= MIN_PY_VERSION (favor newer first)
    preferred = [c for c in cands if c.version_key >= MIN_PY_VERSION] or cands

    console.print("Detected Python interpreters:")
    # Use a compact table style; fall back if Rich version lacks the attribute
    compact_box = getattr(box, "MINIMAL_HEAVY_HEAD", None) or getattr(box, "SIMPLE_HEAVY", None) or getattr(box, "SIMPLE", None)
    table = Table(box=compact_box)
    table.add_column("#")
    table.add_column("Path")
    table.add_column("Version")
    table.add_column("Source")

    for idx, c in enumerate(preferred, 1):
        table.add_row(str(idx), str(c.path), c.version or "?", c.source)
    console.print(table)

    default_idx = 1
    prompt = f"Select [1-{len(preferred)}] or enter a custom path"
    resp = Prompt.ask(prompt, default=str(default_idx))

    # If the response is a valid index
    if resp.isdigit():
        i = int(resp)
        if 1 <= i <= len(preferred):
            return preferred[i - 1].path

    # Otherwise, treat as a filesystem path
    p = Path(os.path.expanduser(resp)).resolve()
    if not p.exists():
        console.print(f"[red]Path not found:[/red] {p}")
        raise SystemExit(2)
    return p


def resolve_python_selection_interactive(
    requirements: Path,
    glyphs_version: Literal["3", "4"] = "4",
    skip_deps: bool = False,
) -> None:
    if skip_deps:
        console.print("[yellow]Skipping Python dependency installation.[/yellow]")
        return

    choice = choose_mode()
    if choice == "1":
        install_with_glyphs_python(requirements, glyphs_version=glyphs_version)
        return

    cands = detect_python_candidates()
    if not cands:
        console.print("[yellow]No Python interpreters detected. You can enter a custom path.[/yellow]")
    python_path = choose_custom_python(cands)
    ver = python_version(python_path) or "unknown"
    vt = version_tuple(ver)
    if vt >= MAX_PY_VERSION_EXCLUSIVE:
        console.print(f"[red]Python {ver} is not yet supported. Please use 3.11–3.14.[/red]")
        raise SystemExit(2)
    if vt < MIN_PY_VERSION:
        proceed = Confirm.ask(f"Selected Python {ver} is older than {MIN_PY_VERSION[0]}.{MIN_PY_VERSION[1]}. Continue?", default=False)
        if not proceed:
            console.print(f"[red]Aborting. Please install Python {MIN_PY_VERSION[0]}.{MIN_PY_VERSION[1]}+ and re-run.[/red]")
            raise SystemExit(2)
    install_with_custom_python(python_path, requirements)


def resolve_python_selection_non_interactive(options: InstallerOptions, requirements: Path) -> None:
    if options.skip_deps:
        console.print("[yellow]Skipping Python dependency installation.[/yellow]")
        return

    if options.python_mode == "glyphs":
        install_with_glyphs_python(requirements, glyphs_version=options.glyphs_version)
        return

    assert options.python_mode == "custom"
    assert options.python_path is not None
    ver = python_version(options.python_path) or "unknown"
    vt = version_tuple(ver)
    if vt >= MAX_PY_VERSION_EXCLUSIVE:
        raise SystemExit(f"Python {ver} is not yet supported. Please use 3.11–3.14.")
    if vt < MIN_PY_VERSION:
        raise SystemExit(f"Selected Python {ver} is older than {MIN_PY_VERSION[0]}.{MIN_PY_VERSION[1]}.")
    install_with_custom_python(options.python_path, requirements)


def choose_plugin_mode_interactive() -> str:
    console.print()
    console.rule("Plugin Installation Mode")
    console.print("Choose how to install the plug‑in into the Glyphs Plugins folder:")
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Option")
    table.add_column("Mode")
    table.add_column("Description")
    table.add_row("1", "Copy", "Copies the bundle (recommended for users)")
    table.add_row("2", "Link", "Creates a symlink to the repo (dev mode)")
    console.print(table)
    install_choice = Prompt.ask("Enter 1 or 2", choices=["1", "2"], default="1")
    return "link" if install_choice == "2" else "copy"


def skill_targets_from_option(skills_target: Literal["codex", "claude", "both"]) -> List[Tuple[str, Path]]:
    if skills_target == "codex":
        return [("Codex", codex_skills_dir())]
    if skills_target == "claude":
        return [("Claude Code", claude_code_skills_dir())]
    return [("Codex", codex_skills_dir()), ("Claude Code", claude_code_skills_dir())]


# MARK: - Safe uninstall

def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _uninstall_versions(selection: Literal["3", "4", "both"]) -> Tuple[Literal["3", "4"], ...]:
    if selection == "both":
        return ("3", "4")
    return (selection,)


def _read_codex_server_block(toml: str) -> Optional[Tuple[int, int, Optional[str]]]:
    lines = toml.splitlines(keepends=True)
    header = f"[mcp_servers.{CODEX_SERVER_NAME}]"
    start: Optional[int] = None
    for index, line in enumerate(lines):
        if line.strip() == header:
            start = index
            break
    if start is None:
        return None

    end = len(lines)
    url: Optional[str] = None
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("["):
            end = index
            break
        match = re.match(r"^url\s*=\s*(['\"])(.*?)\1\s*(?:#.*)?$", stripped)
        if match:
            url = match.group(2)
    return start, end, url


def inspect_codex_config(path: Path) -> Tuple[str, str]:
    if not path.exists():
        return "missing", "Configuration file not found."
    try:
        toml = path.read_text(encoding="utf-8")
    except Exception as error:
        return "blocked", f"Could not read configuration: {error}"
    block = _read_codex_server_block(toml)
    if block is None:
        return "missing", f"No {CODEX_SERVER_NAME} entry."
    if block[2] != MCP_ENDPOINT:
        return "preserved", "A same-named entry has a different URL and is treated as user-managed."
    return "removable", "Matching Glyphs MCP Codex entry."


def remove_codex_config_entry(path: Path) -> bool:
    toml = path.read_text(encoding="utf-8")
    block = _read_codex_server_block(toml)
    if block is None or block[2] != MCP_ENDPOINT:
        return False
    start, end, _url = block
    lines = toml.splitlines(keepends=True)
    del lines[start:end]
    updated = "".join(lines)
    _backup_file(path)
    path.write_text(updated, encoding="utf-8")
    return True


def _load_json_object(path: Path) -> Tuple[Optional[dict], Optional[str]]:
    if not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        return None, f"Could not parse configuration: {error}"
    if not isinstance(data, dict):
        return None, "The configuration root is not a JSON object."
    return data, None


def _json_server(path: Path, server_name: str) -> Tuple[Optional[dict], Optional[str]]:
    root, error = _load_json_object(path)
    if error or root is None:
        return None, error
    servers = root.get("mcpServers")
    if servers is None:
        return None, None
    if not isinstance(servers, dict):
        return None, "The mcpServers value is not a JSON object."
    server = servers.get(server_name)
    if server is None:
        return None, None
    if not isinstance(server, dict):
        return None, "The matching server entry is not a JSON object."
    return server, None


def inspect_claude_code_config(path: Path) -> Tuple[str, str]:
    if not path.exists():
        return "missing", "Configuration file not found."
    server, error = _json_server(path, CLAUDE_CODE_SERVER_NAME)
    if error:
        return "blocked", error
    if server is None:
        return "missing", f"No {CLAUDE_CODE_SERVER_NAME} entry."
    if server.get("type") != "http" or server.get("url") != MCP_ENDPOINT:
        return "preserved", "A same-named entry has a different transport or URL and is treated as user-managed."
    return "removable", "Matching Glyphs MCP Claude Code entry."


def inspect_claude_desktop_config(path: Path) -> Tuple[str, str]:
    if not path.exists():
        return "missing", "Configuration file not found."
    server, error = _json_server(path, CLAUDE_DESKTOP_SERVER_NAME)
    if error:
        return "blocked", error
    if server is None:
        return "missing", f"No {CLAUDE_DESKTOP_SERVER_NAME} entry."
    args = server.get("args")
    matches_args = (
        isinstance(args, list)
        and all(isinstance(value, str) for value in args)
        and "mcp-remote" in args
        and MCP_ENDPOINT in args
    )
    if server.get("command") != "npx" or not matches_args:
        return "preserved", "A same-named entry has a different command or endpoint and is treated as user-managed."
    return "removable", "Matching Glyphs MCP Claude Desktop entry."


def remove_json_config_entry(
    path: Path,
    client_kind: Literal["claude-desktop", "claude-code"],
    server_name: str,
) -> bool:
    state, _detail = (
        inspect_claude_desktop_config(path)
        if client_kind == "claude-desktop"
        else inspect_claude_code_config(path)
    )
    if state != "removable":
        return False
    root, error = _load_json_object(path)
    if error or root is None:
        return False
    servers = root.get("mcpServers")
    if not isinstance(servers, dict) or server_name not in servers:
        return False
    updated_servers = dict(servers)
    del updated_servers[server_name]
    updated_root = dict(root)
    updated_root["mcpServers"] = updated_servers
    _backup_file(path)
    path.write_text(json.dumps(updated_root, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def _backup_file(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = path.with_name(f"{path.name}.bak-{timestamp}")
    shutil.copy2(path, backup)
    return backup


def build_uninstall_plan(
    glyphs_version: Literal["3", "4", "both"] = "4",
    components: Optional[FrozenSet[str]] = None,
) -> GlyphsUninstallPlan:
    selected_components = UNINSTALL_COMPONENTS if components is None else components
    candidates: List[UninstallCandidate] = []

    if "plugin" in selected_components:
        for version in _uninstall_versions(glyphs_version):
            path = glyphs_plugins_dir(version) / "Glyphs MCP.glyphsPlugin"
            exists = _path_exists(path)
            candidates.append(UninstallCandidate(
                identifier=f"plugin-{version}",
                component="plugin",
                label=f"Glyphs {version} plug-in",
                location=path,
                state="removable" if exists else "missing",
                detail=("Development symlink; only the link will be removed." if path.is_symlink() else "Installed plug-in bundle.") if exists else "Not installed.",
                glyphs_version=version,
            ))

    if "skills" in selected_components:
        for client_name, root in (("Codex", codex_skills_dir()), ("Claude Code", claude_code_skills_dir())):
            for skill_name in MANAGED_SKILL_NAMES:
                path = root / skill_name
                if not _path_exists(path):
                    continue
                candidates.append(UninstallCandidate(
                    identifier=f"skill-{client_name.lower().replace(' ', '-')}-{skill_name}",
                    component="skills",
                    label=f"{client_name} skill: {skill_name}",
                    location=path,
                    state="removable",
                    detail="Exact managed skill destination.",
                ))

    if "clients" in selected_components:
        client_specs = (
            ("codex", "Codex MCP entry", codex_config_path(), inspect_codex_config),
            ("claude-desktop", "Claude Desktop MCP entry", claude_desktop_config_path(), inspect_claude_desktop_config),
            ("claude-code", "Claude Code MCP entry", claude_code_config_path(), inspect_claude_code_config),
        )
        for client_kind, label, path, inspector in client_specs:
            state, detail = inspector(path)
            candidates.append(UninstallCandidate(
                identifier=f"client-{client_kind}",
                component="clients",
                label=label,
                location=path,
                state=state,
                detail=detail,
                client_kind=client_kind,
            ))

    return GlyphsUninstallPlan(frozenset(selected_components), tuple(candidates))


def print_uninstall_plan(plan: GlyphsUninstallPlan) -> None:
    console.rule("Glyphs MCP Uninstaller")
    console.print(Panel.fit(
        "Only the exact selected plug-in bundles, managed skill folders, and matching MCP client entries can be removed.\n\n"
        "PRESERVED: all Python packages and site-packages folders, Glyphs preferences, plug-in settings, "
        "font annotations and other user data, repositories, documents, and shared parent folders.",
        title="Important — review before continuing",
        border_style="red",
    ))
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Component")
    table.add_column("Status")
    table.add_column("Location")
    table.add_column("Details")
    if not plan.candidates:
        table.add_row("None", "Nothing detected", "—", "No selected component has an installed artifact.")
    for candidate in plan.candidates:
        table.add_row(candidate.label, candidate.state.replace("-", " ").title(), str(candidate.location), candidate.detail)
    console.print(table)


def _running_glyphs_versions() -> FrozenSet[str]:
    try:
        output = subprocess.check_output(["ps", "-ax", "-o", "command="], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        # Fail closed when a selected plug-in would be removed. Callers treat
        # this marker as a verification failure rather than assuming Glyphs is closed.
        return frozenset({"unknown"})

    versions: set[str] = set()
    app_pattern = re.compile(r"^\s*(?P<path>/.*?/Glyphs[^/]*?\.app)/Contents/MacOS/", re.IGNORECASE)
    for line in output.splitlines():
        if "glyphs" not in line.lower() or ".app/Contents/MacOS/" not in line:
            continue
        match = app_pattern.search(line)
        if not match:
            continue
        app_path = Path(match.group("path"))
        info: dict = {}
        try:
            with (app_path / "Contents" / "Info.plist").open("rb") as handle:
                loaded = plistlib.load(handle)
                if isinstance(loaded, dict):
                    info = loaded
        except Exception:
            pass
        version_text = str(info.get("CFBundleShortVersionString", ""))
        bundle_id = str(info.get("CFBundleIdentifier", "")).lower()
        name_text = app_path.stem.lower()
        major = version_text.split(".", 1)[0]
        if major in {"3", "4"}:
            versions.add(major)
        elif "glyphs3" in bundle_id or re.search(r"glyphs\s*3", name_text):
            versions.add("3")
        elif "glyphs4" in bundle_id or re.search(r"glyphs\s*4", name_text):
            versions.add("4")
        else:
            versions.add("unknown")
    return frozenset(versions)


def execute_uninstall_plan(plan: GlyphsUninstallPlan) -> Tuple[UninstallOutcome, ...]:
    outcomes: List[UninstallOutcome] = []
    for candidate in plan.candidates:
        if candidate.state != "removable":
            outcomes.append(UninstallOutcome(candidate, "skipped", candidate.detail))
            continue
        try:
            if candidate.component in {"plugin", "skills"}:
                if not _path_exists(candidate.location):
                    outcomes.append(UninstallOutcome(candidate, "skipped", "Already absent."))
                    continue
                _remove_existing_path(candidate.location)
            elif candidate.client_kind == "codex":
                state, detail = inspect_codex_config(candidate.location)
                if state != "removable" or not remove_codex_config_entry(candidate.location):
                    outcomes.append(UninstallOutcome(candidate, "skipped", detail))
                    continue
            elif candidate.client_kind == "claude-code":
                state, detail = inspect_claude_code_config(candidate.location)
                if state != "removable" or not remove_json_config_entry(candidate.location, "claude-code", CLAUDE_CODE_SERVER_NAME):
                    outcomes.append(UninstallOutcome(candidate, "skipped", detail))
                    continue
            elif candidate.client_kind == "claude-desktop":
                state, detail = inspect_claude_desktop_config(candidate.location)
                if state != "removable" or not remove_json_config_entry(candidate.location, "claude-desktop", CLAUDE_DESKTOP_SERVER_NAME):
                    outcomes.append(UninstallOutcome(candidate, "skipped", detail))
                    continue
            outcomes.append(UninstallOutcome(candidate, "removed", "Removed."))
        except Exception as error:
            outcomes.append(UninstallOutcome(candidate, "failed", str(error)))
    return tuple(outcomes)


def run_uninstall(options: InstallerOptions) -> None:
    components = options.uninstall_components or UNINSTALL_COMPONENTS
    plan = build_uninstall_plan(options.glyphs_version, components)
    print_uninstall_plan(plan)

    if not options.non_interactive and not options.uninstall_components and not options.dry_run:
        chosen: set[str] = set()
        prompts = (
            ("plugin", "Remove detected Glyphs MCP plug-in bundles?"),
            ("skills", "Remove detected managed Codex and Claude Code skills?"),
            ("clients", "Remove matching Glyphs MCP client configuration entries?"),
        )
        for component, prompt in prompts:
            if any(candidate.component == component and candidate.state == "removable" for candidate in plan.candidates):
                if Confirm.ask(prompt, default=True):
                    chosen.add(component)
        plan = build_uninstall_plan(options.glyphs_version, frozenset(chosen))
        console.print("\n[bold]Final removal selection:[/bold]")
        print_uninstall_plan(plan)

    if options.dry_run:
        console.print("[cyan]Dry run complete. No files were changed.[/cyan]")
        return

    removable = plan.removable_candidates
    if not removable:
        console.print("[green]Nothing safely attributable is installed for the selected targets.[/green]")
        return

    plugin_versions = frozenset(
        candidate.glyphs_version
        for candidate in removable
        if candidate.component == "plugin" and candidate.glyphs_version is not None
    )
    running_detection = _running_glyphs_versions()
    if "unknown" in running_detection and plugin_versions:
        console.print("[red]Could not safely verify whether the selected Glyphs apps are closed. Quit Glyphs and re-run the uninstall.[/red]")
        raise SystemExit(2)
    running = running_detection.intersection(plugin_versions)
    if running:
        names = ", ".join(f"Glyphs {version}" for version in sorted(running))
        console.print(f"[red]{names} must be quit before removing the selected plug-in.[/red]")
        raise SystemExit(2)

    if not options.non_interactive:
        confirmed = Confirm.ask(
            "I understand the listed items will be removed while Python packages, settings, and user data are preserved. Continue?",
            default=False,
        )
        if not confirmed:
            console.print("[yellow]Uninstall cancelled. Nothing was changed.[/yellow]")
            raise SystemExit(3)

    outcomes = execute_uninstall_plan(plan)
    console.rule("Uninstall results")
    for outcome in outcomes:
        color = "green" if outcome.status == "removed" else "red" if outcome.status == "failed" else "yellow"
        console.print(f"[{color}]{outcome.status.upper()}[/{color}] {outcome.candidate.label}: {outcome.message}")
    console.print("[cyan]Python packages, Glyphs settings, font data, and shared folders were preserved.[/cyan]")
    if any(outcome.status == "failed" for outcome in outcomes):
        raise SystemExit(1)
    console.print("[green]Glyphs MCP uninstall complete.[/green]")


def run_non_interactive(options: InstallerOptions, requirements: Path) -> None:
    resolve_python_selection_non_interactive(options, requirements)

    assert options.plugin_mode is not None
    dest = glyphs_plugins_dir(options.glyphs_version) / "Glyphs MCP.glyphsPlugin"
    if (dest.exists() or dest.is_symlink()) and options.overwrite_plugin is None:
        raise SystemExit(format_missing_policy_error("plug-in installation", "--overwrite-plugin", "--keep-plugin"))
    install_plugin(options.plugin_mode, overwrite_existing=options.overwrite_plugin, glyphs_version=options.glyphs_version)

    if options.install_skills:
        assert options.skills_target is not None
        targets = skill_targets_from_option(options.skills_target)
        install_skill_bundle_for_targets(targets, overwrite_existing=options.overwrite_skills, non_interactive=True)

    console.rule("[green]Install complete[/green]")
    console.print("Open Glyphs and use [bold]Edit → Glyphs MCP Server[/bold].")
    if options.show_client_guidance:
        show_client_guidance()


def run_interactive(requirements: Path, options: Optional[InstallerOptions] = None) -> None:
    if options is None:
        options = InstallerOptions(non_interactive=False)

    resolve_python_selection_interactive(
        requirements,
        glyphs_version=options.glyphs_version,
        skip_deps=options.skip_deps,
    )
    mode = choose_plugin_mode_interactive()
    install_plugin(mode, glyphs_version=options.glyphs_version)
    prompt_install_skill_bundle()

    console.rule("[green]Install complete[/green]")
    console.print("Open Glyphs and use [bold]Edit → Glyphs MCP Server[/bold].")

    if Confirm.ask("Show MCP client configuration instructions?", default=True):
        show_client_guidance()


def main(argv: Optional[List[str]] = None) -> None:
    parsed = parse_cli_options(argv)
    if parsed.uninstall:
        run_uninstall(parsed)
        return

    req = repo_root() / "requirements.txt"
    if not req.exists():
        console.print("[red]requirements.txt not found[/red]")
        raise SystemExit(2)

    if parsed.non_interactive:
        run_non_interactive(parsed, req)
    else:
        run_interactive(req, parsed)

    console.print()
    console.rule("Thanks ✨")
    console.print(
        "If this plug‑in helps your workflow, please consider starring the repo\n"
        "and opening issues with ideas or bugs — it really helps improve things!\n\n"
        "GitHub: https://github.com/thierryc/Glyphs-mcp\n"
        "Issues: https://github.com/thierryc/Glyphs-mcp/issues"
    )


def show_client_guidance() -> None:
    console.rule("MCP Client Setup")
    url = "http://127.0.0.1:9680/mcp/"
    console.print(Panel.fit(
        "Link the local Glyphs MCP server with these direct HTTP commands:\n\n"
        "Codex:\n"
        f"  codex mcp add glyphs-mcp-server --url {url}\n"
        "  codex mcp list\n\n"
        "Claude Code:\n"
        f"  claude mcp add --scope user --transport http glyphs-mcp {url}\n"
        "  claude mcp list\n\n"
        "Then open Glyphs and run Edit → Glyphs MCP Server.",
        title="Codex + Claude Code",
        border_style="cyan",
    ))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Command failed with exit code {e.returncode}[/red]")
        raise SystemExit(e.returncode)
