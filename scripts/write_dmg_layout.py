#!/usr/bin/env python3
"""Write fresh Finder metadata on a writable DMG; never automate Finder.

Build-only dependencies are pinned in dmg-layout-requirements.txt. This helper
is not included in the application or its runtime.
"""

import argparse
from importlib.metadata import version
from pathlib import Path

from ds_store import DSStore
from mac_alias import Alias


def write_layout(folder: Path, app_name: str) -> None:
    for package, expected in (("ds_store", "1.3.3"), ("mac_alias", "2.2.3")):
        if version(package) != expected:
            raise ValueError(f"Install the pinned build dependency {package}=={expected}")
    folder = folder.resolve(strict=True)
    if not folder.is_mount():
        raise ValueError("Layout target must be a mounted volume")
    if Path(app_name).name != app_name or not app_name.endswith(".app"):
        raise ValueError("App name must be a single .app filename")
    if not (folder / app_name).is_dir():
        raise ValueError("Application missing from mounted volume")
    shortcut = folder / "Applications"
    if not shortcut.is_symlink() or shortcut.resolve() != Path("/Applications"):
        raise ValueError("Applications shortcut must point to /Applications")
    image = folder / ".background/background.tiff"
    if not image.is_file() or image.is_symlink():
        raise ValueError("Background must be a regular file")

    # Mint against this volume's creation time and file IDs. An alias copied
    # from another DMG can silently resolve to a missing background.
    alias = Alias.for_file(str(image))
    name = alias.volume.name
    if isinstance(name, bytes):
        name = name.decode("utf-8")
    alias.volume.posix_path = "/Volumes/" + name
    background = alias.to_bytes()
    window = {
        "ContainerShowSidebar": False,
        "ShowPathbar": False,
        "ShowSidebar": False,
        "ShowStatusBar": False,
        "ShowTabView": False,
        "ShowToolbar": False,
        "WindowBounds": "{{100, 100}, {680, 448}}",
    }
    icons = {
        "arrangeBy": "none",
        "backgroundColorBlue": 1.0,
        "backgroundColorGreen": 1.0,
        "backgroundColorRed": 1.0,
        "backgroundImageAlias": background,
        "backgroundType": 2,
        "gridOffsetX": 0.0,
        "gridOffsetY": 0.0,
        "gridSpacing": 100.0,
        "iconSize": 112.0,
        "labelOnBottom": True,
        "scrollPositionX": 0.0,
        "scrollPositionY": 0.0,
        "showIconPreview": True,
        "showItemInfo": False,
        "textSize": 12.0,
        "viewOptionsVersion": 1,
    }
    target = folder / ".DS_Store"
    if target.is_symlink():
        raise ValueError("Refusing a symlinked .DS_Store")
    with DSStore.open(str(target), "w+") as store:
        store["."]["bwsp"] = window
        store["."]["icvp"] = icons
        store["."]["vstl"] = ("type", b"icnv")
        store[app_name]["Iloc"] = (170, 194)
        store["Applications"]["Iloc"] = (510, 194)
    with DSStore.open(str(target), "r") as store:
        if store[app_name]["Iloc"] != (170, 194) or store["Applications"]["Iloc"] != (510, 194):
            raise ValueError("Icon layout did not persist")
        if store["."]["bwsp"] != window or store["."]["icvp"] != icons:
            raise ValueError("Window/background metadata did not persist")
    print("Fresh DMG layout written and read back successfully")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--app", default="Glyphs MCP.app")
    args = parser.parse_args()
    write_layout(args.folder, args.app)
