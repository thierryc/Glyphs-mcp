#!/usr/bin/env python3
"""
Interactive installer for the Glyphs MCP plug‑in.

This installer:
1. Detects Glyphs Python version from preferences
2. Downloads and vendors dependencies for that Python version
3. Copies or symlinks the plugin into the Glyphs Plugins folder
4. Shows MCP client configuration instructions

Run:
  python src/glyphs-mcp/scripts/install_cli.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

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


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def glyphs_plugins_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "Glyphs 3" / "Plugins"


def plugin_source() -> Path:
    return repo_root() / "src" / "glyphs-mcp" / "Glyphs MCP.glyphsPlugin"


def vendor_dir() -> Path:
    """Return path to the vendor directory."""
    return plugin_source() / "Contents" / "Resources" / "vendor"


def vendor_deps_script() -> Path:
    """Return path to the vendor_deps.py script."""
    return repo_root() / "src" / "glyphs-mcp" / "scripts" / "vendor_deps.py"


def check_vendor_dir() -> bool:
    """Check if vendor directory exists and has packages."""
    vd = vendor_dir()
    if not vd.is_dir():
        return False
    return any(vd.iterdir())


def detect_glyphs_python() -> Tuple[Optional[Path], Optional[str]]:
    """Detect Python configured in Glyphs preferences.

    Returns (python_executable, version_string) or (None, None) if not found.
    """
    try:
        result = subprocess.run(
            ["defaults", "read", "com.GeorgSeifert.Glyphs3", "GSPythonFrameworkPath"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None, None

        framework_path = Path(result.stdout.strip())
        if not framework_path.exists():
            return None, None

        # Extract version from path (e.g., /Library/Frameworks/Python.framework/Versions/3.14)
        version = framework_path.name

        # Find the Python executable
        python_bin = framework_path / "bin" / f"python{version}"
        if not python_bin.exists():
            python_bin = framework_path / "bin" / "python3"
        if not python_bin.exists():
            return None, None

        return python_bin, version
    except Exception:
        return None, None


def get_python_for_vendoring() -> Path:
    """Get Python executable for vendoring dependencies.

    Auto-detect Glyphs Python from preferences, falling back to sys.executable.
    """
    glyphs_python, glyphs_version = detect_glyphs_python()
    if glyphs_python:
        console.print(f"[green]Detected Glyphs Python {glyphs_version}:[/green] {glyphs_python}\n")
        return glyphs_python

    current_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    console.print("[yellow]Could not detect Glyphs Python from preferences.[/yellow]")
    console.print(f"[cyan]Falling back to Python {current_version}:[/cyan] {sys.executable}\n")
    return Path(sys.executable)


def run_vendor_deps(python_exe: Path) -> bool:
    """Run vendor_deps.py with the specified Python. Returns True on success."""
    script = vendor_deps_script()
    if not script.exists():
        console.print(f"[red]vendor_deps.py not found at:[/red] {script}")
        return False

    console.print(f"\n[cyan]Downloading dependencies using:[/cyan] {python_exe}\n")
    try:
        result = subprocess.run([str(python_exe), str(script)])
        return result.returncode == 0
    except KeyboardInterrupt:
        console.print("\n[yellow]Download cancelled.[/yellow]")
        raise


def install_plugin(mode: str = "copy") -> None:
    """Install the plug-in by copying or linking (dev mode)."""
    src = plugin_source()
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


def main() -> None:
    console.rule("Glyphs MCP Installer")

    # Get Python for dependency download
    python_exe = get_python_for_vendoring()

    # Check for vendor directory and offer to download/update
    has_vendor = check_vendor_dir()

    if has_vendor:
        console.print("[green]Vendor directory found with bundled dependencies.[/green]\n")
        if Confirm.ask("Re-download dependencies to get latest versions?", default=False):
            if not run_vendor_deps(python_exe):
                console.print("[red]Failed to download dependencies.[/red]")
                raise SystemExit(1)
            console.print("[green]Dependencies updated successfully![/green]\n")
    else:
        console.print("[yellow]Vendor directory is empty or missing.[/yellow]\n")
        if Confirm.ask("Download dependencies now? (requires internet)", default=True):
            if not run_vendor_deps(python_exe):
                console.print("[red]Failed to download dependencies.[/red]")
                raise SystemExit(1)
            console.print("[green]Dependencies downloaded successfully![/green]\n")
        else:
            console.print(
                "[yellow]Skipping dependency download.[/yellow]\n"
                "The plugin will not work without dependencies.\n"
                "You can run 'python scripts/vendor_deps.py' later.\n"
            )
            if not Confirm.ask("Continue anyway?", default=False):
                raise SystemExit(1)

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
        ("2", "Claude Code"),
        ("3", "GitHub Copilot (VS Code)"),
        ("4", "Continue (VS Code / JetBrains)"),
        ("5", "Cursor IDE"),
        ("6", "Windsurf"),
        ("7", "Codex (OpenAI)"),
        ("8", "Gemini CLI"),
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
            "1. Use the claude CLI command:\n"
            f"   claude mcp add -t http glyphs {url}\n\n"
            "   Add -s user for user-wide config, or -s project for current project only.\n\n"
            "2. Enable MCP discovery so Claude Code (in VS Code) picks up servers from Claude Desktop:\n"
            "   - In VS Code, set: chat.mcp.discovery.enabled = true\n"
            "   - Then register the server in Claude Desktop as shown above.",
            title="Claude Code", border_style="cyan"))

    elif choice == "3":
        console.print(Panel.fit(
            "GitHub Copilot (VS Code) → Add to .vscode/mcp.json in your project:\n\n"
            "{\n"
            '  "servers": {\n'
            '    "glyphs": {\n'
            '      "type": "http",\n'
            f'      "url": "{url}"\n'
            "    }\n"
            "  }\n"
            "}\n\n"
            "Requires VS Code 1.99+ with chat.mcp.enabled and chat.agent.enabled set to true.",
            title="GitHub Copilot", border_style="green"))

    elif choice == "4":
        console.print(Panel.fit(
            "Continue (VS Code / JetBrains) → Add to ~/.continue/config.yaml or workspace .continue/config.yaml:\n\n" +
            "mcpServers:\n"
            "  - name: Glyphs MCP\n"
            "    type: streamable-http\n"
            f"    url: {url}\n",
            title="Continue", border_style="green"))

    elif choice == "5":
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

    elif choice == "6":
        console.print(Panel.fit(
            "Windsurf → Add to ~/.codeium/windsurf/mcp_config.json:\n\n" +
            '{\n'
            '  "mcpServers": {\n'
            '    "glyphs-mcp-server": {\n'
            '      "serverUrl": "' + url + '"\n'
            '    }\n'
            '  }\n'
            '}', title="Windsurf", border_style="magenta"))

    elif choice == "7":
        console.print(Panel.fit(
            "OpenAI Codex CLI → Add to ~/.codex/config.toml:\n\n" +
            "[mcp_servers.glyphs-app-mcp]\n"
            'command = "npx"\n'
            f'args = ["mcp-remote", "{url}", "--header"]\n',
            title="Codex (OpenAI)", border_style="blue"))

    elif choice == "8":
        console.print(Panel.fit(
            "Gemini CLI → Add to ~/.gemini/settings.json (user-wide) or .gemini/settings.json (project):\n\n"
            "{\n"
            '  "mcpServers": {\n'
            '    "glyphs": {\n'
            f'      "httpUrl": "{url}"\n'
            "    }\n"
            "  }\n"
            "}",
            title="Gemini CLI", border_style="blue"))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Command failed with exit code {e.returncode}[/red]")
        raise SystemExit(e.returncode)
