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
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional, Tuple

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
MIN_PY_VERSION = (3, 11, 0)  # Allow 3.11+, prefer 3.12+
MAX_PY_VERSION_EXCLUSIVE = (3, 14, 0)  # Disallow 3.14+ until tested
SKILL_PREFIX = "glyphs-mcp-"


@dataclass
class InstallerOptions:
    non_interactive: bool
    python_mode: Optional[Literal["glyphs", "custom"]] = None
    python_path: Optional[Path] = None
    plugin_mode: Optional[Literal["copy", "link"]] = None
    install_skills: Optional[bool] = None
    skills_target: Optional[Literal["codex", "claude", "both"]] = None
    overwrite_plugin: Optional[bool] = None
    overwrite_skills: Optional[bool] = None
    show_client_guidance: Optional[bool] = None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def glyphs_base_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Glyphs 3"


def glyphs_plugins_dir() -> Path:
    return glyphs_base_dir() / "Plugins"


def glyphs_scripts_site_packages() -> Path:
    return glyphs_base_dir() / "Scripts" / "site-packages"


def codex_skills_dir() -> Path:
    return Path.home() / ".codex" / "skills"


def claude_code_skills_dir() -> Path:
    return Path.home() / ".claude" / "skills"


def glyphs_python_pip() -> Optional[Path]:
    base = glyphs_base_dir() / "Repositories" / "GlyphsPythonPlugin" / "Python.framework"
    pip = base / "Versions" / "Current" / "bin" / "pip3"
    return pip if pip.exists() else None


def glyphs_python_bin() -> Optional[Path]:
    pip = glyphs_python_pip()
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
        python_mode=ns.python_mode,
        python_path=python_path,
        plugin_mode=ns.plugin_mode,
        install_skills=install_skills,
        skills_target=ns.skills_target,
        overwrite_plugin=overwrite_plugin,
        overwrite_skills=overwrite_skills,
        show_client_guidance=show_client_guidance,
    )
    validate_options(options, parser)
    return options


def validate_options(options: InstallerOptions, parser: argparse.ArgumentParser) -> None:
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
        if options.python_mode is None:
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


def verify_runtime(python: Path) -> bool:
    """Verify required packages import cleanly in the selected Python.

    Returns True on success, False otherwise, and prints guidance.
    """
    console.print(Panel.fit(f"Verifying runtime imports in: {python}", title="Verify", border_style="white"))
    code = (
        "import sys;\n"
        "mods=['mcp','fastmcp','pydantic_core','starlette','uvicorn','httpx','sse_starlette','typing_extensions','fontParts','fontTools'];\n"
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
                "If using Apple Silicon, ensure you are using the native arm64 Python (not Rosetta) and matching wheels."
            )
            return False
        return True
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Verification failed to run:[/red] {e}")
        return False


def run(cmd: List[str]) -> None:
    console.log(f"[dim]$ {' '.join(cmd)}[/dim]")
    subprocess.check_call(cmd)


def install_with_glyphs_python(requirements: Path) -> None:
    pip = glyphs_python_pip()
    if not pip:
        console.print("[red]Glyphs Python not found.[/red]")
        console.print("Open Glyphs → Settings → Addons and install Python (GlyphsPythonPlugin), then re-run.")
        raise SystemExit(2)

    target = glyphs_scripts_site_packages()
    target.mkdir(parents=True, exist_ok=True)
    console.print(Panel.fit(f"Installing requirements into:\n{target}", title="Glyphs Python", border_style="green"))
    run([str(pip), "install", "--upgrade", "pip"])
    run([str(pip), "install", "--target", str(target), "-r", str(requirements)])

    # Verify using the interpreter next to pip (../python3)
    glyphs_python = Path(pip).parent / "python3"
    if glyphs_python.exists():
        verify_runtime(glyphs_python)


def install_with_custom_python(python: Path, requirements: Path) -> None:
    console.print(Panel.fit(f"Installing requirements to user site for:\n{python}"
                           f"\n(version: {python_version(python) or 'unknown'})",
                           title="Custom Python", border_style="cyan"))
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python), "-m", "pip", "install", "--user", "-r", str(requirements)])
    verify_runtime(python)


def install_plugin(mode: str = "copy", overwrite_existing: Optional[bool] = None) -> bool:
    """Install the plug-in by copying or linking (dev mode)."""
    src = repo_root() / "src" / "glyphs-mcp" / "Glyphs MCP.glyphsPlugin"
    if not src.exists():
        console.print(f"[red]Plugin bundle not found at:[/red] {src}")
        raise SystemExit(2)

    dest_dir = glyphs_plugins_dir()
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


def resolve_python_selection_interactive(requirements: Path) -> None:
    choice = choose_mode()
    if choice == "1":
        install_with_glyphs_python(requirements)
        return

    cands = detect_python_candidates()
    if not cands:
        console.print("[yellow]No Python interpreters detected. You can enter a custom path.[/yellow]")
    python_path = choose_custom_python(cands)
    ver = python_version(python_path) or "unknown"
    vt = version_tuple(ver)
    if vt >= MAX_PY_VERSION_EXCLUSIVE:
        console.print(f"[red]Python {ver} is not yet supported. Please use 3.11–3.13.[/red]")
        raise SystemExit(2)
    if vt < MIN_PY_VERSION:
        proceed = Confirm.ask(f"Selected Python {ver} is older than {MIN_PY_VERSION[0]}.{MIN_PY_VERSION[1]}. Continue?", default=False)
        if not proceed:
            console.print(f"[red]Aborting. Please install Python {MIN_PY_VERSION[0]}.{MIN_PY_VERSION[1]}+ and re-run.[/red]")
            raise SystemExit(2)
    install_with_custom_python(python_path, requirements)


def resolve_python_selection_non_interactive(options: InstallerOptions, requirements: Path) -> None:
    if options.python_mode == "glyphs":
        install_with_glyphs_python(requirements)
        return

    assert options.python_mode == "custom"
    assert options.python_path is not None
    ver = python_version(options.python_path) or "unknown"
    vt = version_tuple(ver)
    if vt >= MAX_PY_VERSION_EXCLUSIVE:
        raise SystemExit(f"Python {ver} is not yet supported. Please use 3.11–3.13.")
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


def run_non_interactive(options: InstallerOptions, requirements: Path) -> None:
    resolve_python_selection_non_interactive(options, requirements)

    assert options.plugin_mode is not None
    dest = glyphs_plugins_dir() / "Glyphs MCP.glyphsPlugin"
    if (dest.exists() or dest.is_symlink()) and options.overwrite_plugin is None:
        raise SystemExit(format_missing_policy_error("plug-in installation", "--overwrite-plugin", "--keep-plugin"))
    install_plugin(options.plugin_mode, overwrite_existing=options.overwrite_plugin)

    if options.install_skills:
        assert options.skills_target is not None
        targets = skill_targets_from_option(options.skills_target)
        install_skill_bundle_for_targets(targets, overwrite_existing=options.overwrite_skills, non_interactive=True)

    console.rule("[green]Install complete[/green]")
    console.print("Open Glyphs and use [bold]Edit → Start MCP Server[/bold].")
    if options.show_client_guidance:
        show_client_guidance()


def run_interactive(requirements: Path) -> None:
    resolve_python_selection_interactive(requirements)
    mode = choose_plugin_mode_interactive()
    install_plugin(mode)
    prompt_install_skill_bundle()

    console.rule("[green]Install complete[/green]")
    console.print("Open Glyphs and use [bold]Edit → Start MCP Server[/bold].")

    if Confirm.ask("Show MCP client configuration instructions?", default=True):
        show_client_guidance()


def main(argv: Optional[List[str]] = None) -> None:
    req = repo_root() / "requirements.txt"
    if not req.exists():
        console.print("[red]requirements.txt not found[/red]")
        raise SystemExit(2)

    parsed = parse_cli_options(argv)
    if parsed.non_interactive:
        run_non_interactive(parsed, req)
    else:
        run_interactive(req)

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
        "Then open Glyphs and run Edit → Start MCP Server.",
        title="Codex + Claude Code",
        border_style="cyan",
    ))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Command failed with exit code {e.returncode}[/red]")
        raise SystemExit(e.returncode)
