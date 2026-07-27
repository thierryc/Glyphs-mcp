#!/usr/bin/env python3
"""Create and statically validate workspace-first Glyphs scripts and plug-ins."""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import os
import plistlib
import re
import shutil
import stat
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
ASSETS_ROOT = SKILL_ROOT / "assets"
TEMPLATES_ROOT = ASSETS_ROOT / "templates"
PLACEHOLDER_RE = re.compile(r"____[A-Za-z][A-Za-z0-9]*____")
CLASS_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
BUNDLE_VERSION_RE = re.compile(r"^\d+(?:\.\d+)?$")

PLUGIN_SPECS = {
    "general": {
        "suffix": ".glyphsPlugin",
        "template": "general/____PluginName____.glyphsPlugin",
        "base": "GeneralPlugin",
    },
    "reporter": {
        "suffix": ".glyphsReporter",
        "template": "reporter/____PluginName____.glyphsReporter",
        "base": "ReporterPlugin",
    },
    "filter": {
        "suffix": ".glyphsFilter",
        "template": "filter/____PluginName____.glyphsFilter",
        "base": "FilterWithoutDialog",
    },
    "palette": {
        "suffix": ".glyphsPalette",
        "template": "palette/____PluginName____.glyphsPalette",
        "base": "PalettePlugin",
    },
    "select-tool": {
        "suffix": ".glyphsTool",
        "template": "select-tool/____PluginName____.glyphsTool",
        "base": "SelectTool",
    },
    "file-format": {
        "suffix": ".glyphsFileFormat",
        "template": "file-format/____PluginName____.glyphsFileFormat",
        "base": "FileFormatPlugin",
    },
}

SUFFIX_TO_KIND = {
    spec["suffix"]: kind for kind, spec in PLUGIN_SPECS.items()
}


class ScaffoldError(RuntimeError):
    """Raised when a scaffold or validation request is unsafe or invalid."""


def _safe_name(value: str) -> str:
    name = value.strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ScaffoldError("Name must be a non-empty filename without path separators.")
    if any(ord(character) < 32 for character in name):
        raise ScaffoldError("Name cannot contain control characters.")
    return name


def _derive_class_name(name: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", name)
    candidate = "".join(word[:1].upper() + word[1:] for word in words)
    if candidate and candidate[0].isdigit():
        candidate = "Plugin" + candidate
    if not candidate:
        raise ScaffoldError("Provide --class-name for names without ASCII letters or digits.")
    return candidate


def _validate_class_name(value: str) -> str:
    if not CLASS_NAME_RE.fullmatch(value):
        raise ScaffoldError(
            "Class name must start with an ASCII letter and contain only letters, digits, or underscores."
        )
    return value


def _developer_identifier(value: str) -> str:
    identifier = re.sub(r"[^a-z0-9]+", "", value.lower())
    if not identifier:
        raise ScaffoldError("Developer name must contain an ASCII letter or digit.")
    return identifier


def _is_live_glyphs_path(path: Path) -> bool:
    support = (Path.home() / "Library" / "Application Support").resolve()
    resolved = path.expanduser().resolve()
    try:
        relative = resolved.relative_to(support)
    except ValueError:
        return False

    parts = relative.parts
    for index, part in enumerate(parts[:-1]):
        if part.startswith("Glyphs") and parts[index + 1] in {"Scripts", "Plugins"}:
            return True
    return False


def _assert_destination_allowed(path: Path, allow_live_install: bool) -> None:
    if _is_live_glyphs_path(path) and not allow_live_install:
        raise ScaffoldError(
            "Refusing to write into a live Glyphs Scripts or Plugins folder. "
            "Create in the workspace or pass --allow-live-install after explicit user approval."
        )


def _read_utf8(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _replace_text_placeholders(root: Path, replacements: dict[str, str]) -> None:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        text = _read_utf8(path)
        if text is None:
            continue
        updated = text
        for placeholder, value in replacements.items():
            updated = updated.replace(placeholder, value)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def _script_source(name: str, description: str) -> str:
    return f'''# MenuTitle: {name}
# encoding: utf-8

__doc__ = {description!r}

from GlyphsApp import Glyphs


def main():
    font = Glyphs.font
    if font is None:
        raise RuntimeError("Open a font in Glyphs before running this script.")

    # Replace this line with the documented script behavior.
    print("Current font:", font.familyName)


if __name__ == "__main__":
    main()
'''


def _palette_source(class_name: str, name: str) -> str:
    return f'''# encoding: utf-8

import objc
from GlyphsApp import Glyphs
from GlyphsApp.plugins import PalettePlugin
from vanilla import Group, TextBox, Window


class {class_name}(PalettePlugin):

    @objc.python_method
    def settings(self):
        self.name = {name!r}
        width, height = 180, 42
        self.paletteWindow = Window((width, height))
        self.paletteWindow.group = Group((0, 0, width, height))
        self.paletteWindow.group.label = TextBox(
            (10, 10, -10, 20), self.name, sizeStyle="small"
        )
        self.dialog = self.paletteWindow.group.getNSView()

    @objc.python_method
    def start(self):
        pass

    @objc.python_method
    def __file__(self):
        return __file__
'''


def _write_plugin_plist(
    bundle: Path,
    *,
    name: str,
    class_name: str,
    developer: str,
    bundle_version: str,
    short_version: str,
    year: int,
) -> None:
    plist_path = bundle / "Contents" / "Info.plist"
    try:
        payload = plistlib.loads(plist_path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as exc:
        raise ScaffoldError(f"Unable to read SDK Info.plist: {exc}") from exc

    payload["CFBundleIdentifier"] = (
        f"com.{_developer_identifier(developer)}.{class_name}"
    )
    payload["CFBundleName"] = name
    payload["CFBundleShortVersionString"] = short_version
    payload["CFBundleVersion"] = bundle_version
    payload["NSHumanReadableCopyright"] = f"Copyright, {developer}, {year}"
    payload["NSPrincipalClass"] = class_name
    plist_path.write_bytes(plistlib.dumps(payload, sort_keys=False))


def _create_script(args: argparse.Namespace, destination_root: Path) -> Path:
    name = _safe_name(args.name)
    filename = name if name.lower().endswith(".py") else name + ".py"
    menu_name = name[:-3] if name.lower().endswith(".py") else name
    output = destination_root / filename
    _assert_destination_allowed(output, args.allow_live_install)
    if output.exists():
        raise ScaffoldError(f"Refusing to overwrite existing artifact: {output}")
    destination_root.mkdir(parents=True, exist_ok=True)
    output.write_text(_script_source(menu_name, args.description), encoding="utf-8")
    return output


def _create_plugin(args: argparse.Namespace, destination_root: Path) -> Path:
    spec = PLUGIN_SPECS[args.kind]
    name = _safe_name(args.name)
    class_name = _validate_class_name(args.class_name or _derive_class_name(name))
    if not args.developer:
        raise ScaffoldError("--developer is required for plug-in scaffolds.")
    if not BUNDLE_VERSION_RE.fullmatch(args.bundle_version):
        raise ScaffoldError("--bundle-version must be an integer or decimal number.")

    output = destination_root / f"{name}{spec['suffix']}"
    _assert_destination_allowed(output, args.allow_live_install)
    if output.exists():
        raise ScaffoldError(f"Refusing to overwrite existing artifact: {output}")

    source = TEMPLATES_ROOT / spec["template"]
    if not source.is_dir():
        raise ScaffoldError(f"Bundled SDK template is missing: {source}")
    destination_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, output, copy_function=shutil.copy2)

    replacements = {
        "____PluginName____": name,
        "____PluginClassName____": class_name,
        "____Developer____": _developer_identifier(args.developer),
        "____BundleVersion____": args.bundle_version,
        "____BundleVersionString____": args.short_version,
        "____YEAR____": str(args.year),
    }
    _replace_text_placeholders(output, replacements)
    _write_plugin_plist(
        output,
        name=name,
        class_name=class_name,
        developer=args.developer,
        bundle_version=args.bundle_version,
        short_version=args.short_version,
        year=args.year,
    )

    if args.kind == "palette":
        resources = output / "Contents" / "Resources"
        for dialog in (resources / "IBdialog.nib", resources / "IBdialog.xib"):
            if dialog.exists():
                dialog.unlink()
        (resources / "plugin.py").write_text(
            _palette_source(class_name, name), encoding="utf-8"
        )

    return output


def _python_classes(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}


def _unresolved_placeholders(root: Path) -> list[str]:
    unresolved: list[str] = []
    paths = [root] if root.is_file() else sorted(root.rglob("*"))
    for path in paths:
        if not path.is_file():
            continue
        text = _read_utf8(path)
        if text and PLACEHOLDER_RE.search(text):
            unresolved.append(str(path))
    return unresolved


def _validate_script(path: Path, target: str) -> dict[str, Any]:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    text = path.read_text(encoding="utf-8")
    if not any(line.startswith("# MenuTitle:") for line in text.splitlines()[:5]):
        raise ScaffoldError("Glyphs script is missing a # MenuTitle header.")
    unresolved = _unresolved_placeholders(path)
    if unresolved:
        raise ScaffoldError("Unresolved placeholders: " + ", ".join(unresolved))
    return {
        "ok": True,
        "artifact": str(path),
        "kind": "script",
        "target": target,
        "checks": ["python-syntax", "menu-title", "no-placeholders"],
        "runtimeTested": False,
    }


def _validate_plugin(bundle: Path, target: str) -> dict[str, Any]:
    kind = next(
        (kind for suffix, kind in SUFFIX_TO_KIND.items() if bundle.name.endswith(suffix)),
        None,
    )
    if kind is None:
        raise ScaffoldError("Unrecognized Glyphs plug-in bundle suffix.")

    spec = PLUGIN_SPECS[kind]
    plist_path = bundle / "Contents" / "Info.plist"
    source_path = bundle / "Contents" / "Resources" / "plugin.py"
    loader_path = bundle / "Contents" / "MacOS" / "plugin"
    for required in (plist_path, source_path, loader_path):
        if not required.is_file():
            raise ScaffoldError(f"Missing required plug-in file: {required}")

    try:
        plist = plistlib.loads(plist_path.read_bytes())
    except plistlib.InvalidFileException as exc:
        raise ScaffoldError(f"Invalid Info.plist: {exc}") from exc
    principal = plist.get("NSPrincipalClass")
    classes = _python_classes(source_path)
    if principal not in classes:
        raise ScaffoldError(
            f"NSPrincipalClass {principal!r} does not match a class in plugin.py."
        )
    if not plist.get("CFBundleIdentifier") or not plist.get("CFBundleName"):
        raise ScaffoldError("Info.plist is missing bundle identity metadata.")
    if not os.access(loader_path, os.X_OK):
        raise ScaffoldError("Bundled SDK plug-in loader is not executable.")

    unresolved = _unresolved_placeholders(bundle)
    if unresolved:
        raise ScaffoldError("Unresolved placeholders: " + ", ".join(unresolved))

    python_files = sorted(bundle.rglob("*.py"))
    for python_file in python_files:
        ast.parse(python_file.read_text(encoding="utf-8"), filename=str(python_file))

    return {
        "ok": True,
        "artifact": str(bundle),
        "kind": kind,
        "baseClass": spec["base"],
        "principalClass": principal,
        "target": target,
        "checks": [
            "bundle-suffix",
            "python-syntax",
            "valid-plist",
            "principal-class",
            "sdk-loader",
            "no-placeholders",
        ],
        "runtimeTested": False,
    }


def validate_artifact(path: Path, target: str) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise ScaffoldError(f"Artifact does not exist: {resolved}")
    if resolved.is_file() and resolved.suffix.lower() == ".py":
        return _validate_script(resolved, target)
    if resolved.is_dir():
        return _validate_plugin(resolved, target)
    raise ScaffoldError("Artifact must be a .py script or Glyphs plug-in bundle.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and validate workspace-first Glyphs scripts and plug-ins."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a new artifact.")
    create.add_argument("kind", choices=("script", *PLUGIN_SPECS.keys()))
    create.add_argument("--name", required=True, help="Human-facing artifact name.")
    create.add_argument("--description", default="A Glyphs Python script.")
    create.add_argument("--destination", default=".", help="Workspace directory.")
    create.add_argument("--class-name", help="Python principal class for plug-ins.")
    create.add_argument("--developer", help="Human developer name for plug-ins.")
    create.add_argument("--bundle-version", default="1")
    create.add_argument("--short-version", default="0.1.0")
    create.add_argument("--year", type=int, default=dt.date.today().year)
    create.add_argument(
        "--target", choices=("both", "3", "4"), default="both"
    )
    create.add_argument(
        "--allow-live-install",
        action="store_true",
        help="Allow a destination in Glyphs Scripts or Plugins after explicit approval.",
    )

    validate = subparsers.add_parser("validate", help="Validate an artifact.")
    validate.add_argument("artifact")
    validate.add_argument(
        "--target", choices=("both", "3", "4"), default="both"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            result = validate_artifact(Path(args.artifact), args.target)
        else:
            destination_root = Path(args.destination).expanduser().resolve()
            if args.kind == "script":
                output = _create_script(args, destination_root)
            else:
                output = _create_plugin(args, destination_root)
            result = validate_artifact(output, args.target)
            result["created"] = True
            result["attribution"] = str(ASSETS_ROOT / "GlyphsSDK-LICENSE.txt")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, SyntaxError, ScaffoldError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
