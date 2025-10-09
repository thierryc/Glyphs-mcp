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
    print("The installer prefers the 'rich' package for a nicer UI.\n"
          "You can install it with: python3 -m pip install --user rich\n"
          "Continuing with a plain console UI…")
    class _Dummy:
        def __getattr__(self, name):
            def f(*a, **k):
                return None
            return f
    Console = Prompt = Confirm = Table = Panel = Text = _Dummy
    box = _Dummy()
    Console = Console()  # type: ignore


console = Console()


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

    # Explicit python.org "Current" convenience path (user request)
    current_py = Path("/Library/Frameworks/Python.framework/Versions/Current/bin/python3.12")
    if current_py.exists():
        ver = python_version(current_py)
        cands.append(PythonCandidate(current_py, ver, "python.org"))

    # python.org framework installs
    framework = Path("/Library/Frameworks/Python.framework/Versions")
    if framework.exists():
        for vdir in sorted(framework.iterdir()):
            bin_dir = vdir / "bin"
            for name in ("python3.13", "python3.12", "python3"):
                py = bin_dir / name
                if py.exists():
                    ver = python_version(py)
                    cands.append(PythonCandidate(py, ver, "python.org"))
                    break

    # Homebrew common locations
    for path_str in ("/opt/homebrew/bin/python3.13", "/opt/homebrew/bin/python3.12", "/opt/homebrew/bin/python3",
                     "/usr/local/bin/python3.13", "/usr/local/bin/python3.12", "/usr/local/bin/python3"):
        py = Path(path_str)
        if py.exists():
            ver = python_version(py)
            cands.append(PythonCandidate(py, ver, "homebrew"))

    # PATH discovery (last, to avoid duping brew/python.org entries)
    for name in ("python3.13", "python3.12", "python3"):
        path = shutil.which(name)
        if path:
            py = Path(path)
            # Avoid duplicates by path
            if not any(c.path == py for c in cands):
                ver = python_version(py)
                cands.append(PythonCandidate(py, ver, "system"))

    # System Python as fallback
    sys_py = Path("/usr/bin/python3")
    if sys_py.exists() and not any(c.path == sys_py for c in cands):
        ver = python_version(sys_py)
        cands.append(PythonCandidate(sys_py, ver, "system"))

    # Sort best-first: highest version, prefer >= 3.12
    cands.sort(key=lambda c: (c.version_key, c.source != "python.org"), reverse=True)
    return cands


def verify_runtime(python: Path) -> bool:
    """Verify required packages import cleanly in the selected Python.

    Returns True on success, False otherwise, and prints guidance.
    """
    console.print(Panel.fit(f"Verifying runtime imports in: {python}", title="Verify", border_style="white"))
    code = (
        "import sys;\n"
        "mods=['fastmcp','pydantic_core','starlette','uvicorn'];\n"
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
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Option")
    table.add_column("Description")
    table.add_row("1", "Glyphs' Python (Plugin Manager)")
    table.add_row("2", "Custom Python (python.org/Homebrew)")
    console.print(table)
    while True:
        choice = Prompt.ask("Enter 1 or 2", choices=["1", "2"], default="1")
        if choice in ("1", "2"):
            return choice


def choose_custom_python(cands: List[PythonCandidate]) -> Path:
    # Filter preferred >= 3.12
    preferred = [c for c in cands if c.version_key >= (3, 12, 0)] or cands

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
        if version_tuple(ver) < (3, 12, 0):
            proceed = Confirm.ask(f"Selected Python {ver} is older than 3.12. Continue?", default=False)
            if not proceed:
                console.print("[red]Aborting. Please install Python 3.12+ and re-run.[/red]")
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
            "Claude Code (VS Code) → Two common paths:\n\n"
            "1) Enable MCP discovery so Claude Code picks up servers registered by Claude Desktop:\n"
            "   - In VS Code, set: chat.mcp.discovery.enabled = true\n"
            "   - Then register the server in Claude Desktop as shown above.\n\n"
            "2) Or use the Continue extension method below (works with Claude Code too).",
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
