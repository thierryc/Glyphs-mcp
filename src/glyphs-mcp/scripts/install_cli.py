#!/usr/bin/env python3
"""
Interactive installer for the Glyphs MCP plug‑in.

- Lets the user choose between Glyphs' bundled Python or a custom Python.
- Installs Python dependencies accordingly.
- Copies the plug‑in bundle into the Glyphs Plugins folder.

Run:
  python src/glyphs-mcp/scripts/install_cli.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

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


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def glyphs_base_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Glyphs 3"


def glyphs_plugins_dir() -> Path:
    return glyphs_base_dir() / "Plugins"


def glyphs_scripts_site_packages() -> Path:
    return glyphs_base_dir() / "Scripts" / "site-packages"


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

    # Sort best-first: highest version, prefer >= 3.12 and python.org builds
    cands.sort(key=lambda c: (c.version_key, c.source != "python.org"), reverse=True)
    return cands


def verify_runtime(python: Path) -> bool:
    """Verify required packages import cleanly in the selected Python.

    Returns True on success, False otherwise, and prints guidance.
    """
    console.print(Panel.fit(f"Verifying runtime imports in: {python}", title="Verify", border_style="white"))
    code = (
        "import sys;\n"
        "mods=['fastmcp','pydantic_core','starlette','uvicorn','fontParts','fontTools'];\n"
        "missing=[];\n"
        "import importlib;\n"
        "\n"
        "for m in mods:\n"
        "  try:\n"
        "    importlib.import_module(m)\n"
        "  except Exception as e:\n"
        "    missing.append((m,str(e)))\n"
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


def install_plugin(mode: str = "copy") -> None:
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
        overwrite = Confirm.ask(
            f"Plugin already installed as a {current}:\n{dest}\nReplace it?",
            default=True,
        )
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
            return

    if mode == "link":
        console.print(Panel.fit(f"Creating symlink (dev mode) →\n{dest}\n→ {src}", title="Install Plugin", border_style="magenta"))
        os.symlink(src, dest)
    else:
        console.print(Panel.fit(f"Copying plugin →\n{dest}", title="Install Plugin", border_style="magenta"))
        shutil.copytree(src, dest)


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


def main() -> None:
    req = repo_root() / "requirements.txt"
    if not req.exists():
        console.print("[red]requirements.txt not found[/red]")
        raise SystemExit(2)

    choice = choose_mode()
    if choice == "1":
        install_with_glyphs_python(req)
    else:
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
        install_with_custom_python(python_path, req)

    # Ask how to install the plugin: copy (default) or symlink (dev)
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
    mode = "link" if install_choice == "2" else "copy"

    install_plugin(mode)

    console.rule("[green]Install complete[/green]")
    console.print("Open Glyphs and use [bold]Edit → Start MCP Server[/bold].")

    if Confirm.ask("Show MCP client configuration instructions?", default=True):
        show_client_guidance()

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
    clients = [
        ("1", "Claude Desktop"),
        ("2", "Claude Code (VS Code)"),
        ("3", "Continue (VS Code / JetBrains)"),
        ("4", "Cursor IDE"),
        ("5", "Windsurf"),
        ("6", "Codex (OpenAI)")
    ]

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("#")
    table.add_column("Client")
    for key, name in clients:
        table.add_row(key, name)
    console.print(table)

    choice = Prompt.ask("Select a client", choices=[c[0] for c in clients], default="1")
    url = "http://127.0.0.1:9680/mcp/"

    if choice == "1":
        console.print(Panel.fit(
            "Claude Desktop → Add this to your claude_desktop_config.json:\n\n" +
            '{\n'
            '  "mcpServers": {\n'
            '    "glyphs-mcp-server": {\n'
            '      "command": "npx",\n'
            f'      "args": ["mcp-remote", "{url}", "--header"],\n'
            '      "env": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}\n'
            '    }\n'
            '  }\n'
            '}\n\n'
            "Alternatively, using the Python proxy (ensure it's on PATH):\n\n" +
            '{\n'
            '  "mcpServers": {\n'
            '    "glyphs-mcp-server": {\n'
            '      "command": "/Library/Frameworks/Python.framework/Versions/3.12/bin/mcp-proxy",\n'
            '      "args": ["--transport", "streamablehttp", "' + url + '"],\n'
            '      "env": {"PATH": "/Library/Frameworks/Python.framework/Versions/3.12/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}\n'
            '    }\n'
            '  }\n'
            '}', title="Claude Desktop", border_style="cyan"))

    elif choice == "2":
        console.print(Panel.fit(
            "Claude Code → Two options:\n\n"
            "1. Enable MCP discovery so Claude Code (running in VS Code) picks up servers registered by Claude Desktop:\n"
            "   - In VS Code, set: chat.mcp.discovery.enabled = true\n"
            "   - Then register the server in Claude Desktop as shown above.\n"
            "2. Use the claude CLI command\n"
            f"   claude mcp add -t http glyphs {url}\n\n"
            "   Add -s user for user-wide config, or -s project for current project only.\n",
            title="Claude Code", border_style="cyan"))

    elif choice == "3":
        console.print(Panel.fit(
            "Continue (VS Code / JetBrains) → Add to ~/.continue/config.yaml or workspace .continue/config.yaml:\n\n" +
            "mcpServers:\n"
            "  - name: Glyphs MCP\n"
            "    type: streamable-http\n"
            f"    url: {url}\n",
            title="Continue", border_style="green"))

    elif choice == "4":
        console.print(Panel.fit(
            "Cursor IDE → Add to ~/.cursor/mcp.json (ensure Node 20+ in PATH so npx works):\n\n" +
            '{\n'
            '  "mcpServers": {\n'
            '    "glyphs-mcp-server": {\n'
            '      "command": "npx",\n'
            f'      "args": ["mcp-remote", "{url}", "--header"],\n'
            '      "env": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}\n'
            '    }\n'
            '  }\n'
            '}', title="Cursor", border_style="yellow"))

    elif choice == "5":
        console.print(Panel.fit(
            "Windsurf → Add to ~/.codeium/windsurf/mcp_config.json:\n\n" +
            '{\n'
            '  "mcpServers": {\n'
            '    "glyphs-mcp-server": {\n'
            '      "serverUrl": "' + url + '"\n'
            '    }\n'
            '  }\n'
            '}', title="Windsurf", border_style="magenta"))

    elif choice == "6":
        console.print(Panel.fit(
            "OpenAI Codex CLI → Add to ~/.codex/config.toml:\n\n" +
            "[mcp_servers.glyphs-app-mcp]\n"
            'command = "npx"\n'
            f'args = ["mcp-remote", "{url}", "--header"]\n',
            title="Codex (OpenAI)", border_style="blue"))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Command failed with exit code {e.returncode}[/red]")
        raise SystemExit(e.returncode)
