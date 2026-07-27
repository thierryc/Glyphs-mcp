#!/usr/bin/env python3
"""Vendor the pinned official GlyphsSDK Python templates used by the skill."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "GlyphsSDK"
SKILL_ASSETS = REPO_ROOT / "skills" / "glyphs-mcp-development" / "assets"
EXPECTED_REVISION = "0f5422db727b78cb42abfb386f33ae0b382b0c4d"

TEMPLATES = {
    "general": "Python Templates/General Plugin/____PluginName____.glyphsPlugin",
    "reporter": "Python Templates/Reporter/____PluginName____.glyphsReporter",
    "filter": "Python Templates/Filter/without dialog/____PluginName____.glyphsFilter",
    "palette": "Python Templates/Palette/____PluginName____.glyphsPalette",
    "select-tool": "Python Templates/SelectTool/____PluginName____.glyphsTool",
    "file-format": "Python Templates/File Format/dialog with vanilla/____PluginName____.glyphsFileFormat",
}


def _sdk_revision() -> str:
    return subprocess.check_output(
        ["git", "-C", str(SDK_ROOT), "rev-parse", "HEAD"], text=True
    ).strip()


def main() -> int:
    revision = _sdk_revision()
    if revision != EXPECTED_REVISION:
        raise RuntimeError(
            f"GlyphsSDK revision {revision} does not match pinned {EXPECTED_REVISION}."
        )

    templates_root = SKILL_ASSETS / "templates"
    if templates_root.exists():
        shutil.rmtree(templates_root)
    templates_root.mkdir(parents=True)

    loader_hashes: dict[str, str] = {}
    for kind, relative in TEMPLATES.items():
        source = SDK_ROOT / relative
        if not source.is_dir():
            raise FileNotFoundError(source)
        destination = templates_root / kind / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, copy_function=shutil.copy2)
        loader = destination / "Contents" / "MacOS" / "plugin"
        loader_hashes[kind] = hashlib.sha256(loader.read_bytes()).hexdigest()

    shutil.copy2(SDK_ROOT / "LICENSE", SKILL_ASSETS / "GlyphsSDK-LICENSE.txt")
    source_payload = {
        "source": "https://github.com/schriftgestalt/GlyphsSDK",
        "revision": revision,
        "license": "Apache-2.0",
        "templates": TEMPLATES,
        "loaderSha256": loader_hashes,
    }
    (SKILL_ASSETS / "SOURCE.json").write_text(
        json.dumps(source_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Vendored {len(TEMPLATES)} GlyphsSDK Python templates at {revision[:12]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
