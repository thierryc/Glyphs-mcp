"""Guards against drift between the source bundle and the Plugin Manager bundle."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _src_bundle() -> Path:
    return _repo_root() / "src" / "glyphs-mcp" / "Glyphs MCP.glyphsPlugin"


def _plugin_manager_bundle() -> Path:
    return _repo_root() / "plugin-manager" / "Glyphs MCP.glyphsPlugin"


def _ignore_rel_path(rel_path: Path, *, ignore_vendor: bool) -> bool:
    parts = rel_path.parts
    name = rel_path.name
    if any(part in {"__pycache__", "__MACOSX", ".venv", "venv"} for part in parts):
        return True
    if name == ".DS_Store" or name.startswith("._"):
        return True
    if rel_path.suffix in {".pyc", ".pyo"}:
        return True
    if ignore_vendor and parts[:3] == ("Contents", "Resources", "vendor"):
        return True
    return False


def _file_map(bundle_root: Path, *, ignore_vendor: bool) -> dict[Path, Path]:
    files = {}
    for path in bundle_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(bundle_root)
        if _ignore_rel_path(rel, ignore_vendor=ignore_vendor):
            continue
        files[rel] = path
    return files


def _normalized_bytes(path: Path, rel: Path) -> bytes:
    data = path.read_bytes()
    if rel != Path("Contents/Resources/plugin.py"):
        return data

    text = data.decode("utf-8", errors="replace")
    marker_start = "# --- Glyphs MCP Vendor Deps (Plugin Manager build) ---"
    marker_end = "# --- End Glyphs MCP Vendor Deps ---"
    if marker_start in text and marker_end in text:
        pattern = re.compile(
            r"\n?{}.*?{}\n?".format(re.escape(marker_start), re.escape(marker_end)),
            re.S,
        )
        text = pattern.sub("\n", text)
    return text.encode("utf-8")


class PluginManagerBundleSyncTests(unittest.TestCase):
    def test_plugin_manager_bundle_matches_source_bundle(self) -> None:
        src_files = _file_map(_src_bundle(), ignore_vendor=False)
        pm_files = _file_map(_plugin_manager_bundle(), ignore_vendor=True)

        self.assertEqual(sorted(src_files.keys()), sorted(pm_files.keys()))

        for rel, src_path in sorted(src_files.items()):
            pm_path = pm_files[rel]
            self.assertEqual(
                _normalized_bytes(src_path, rel),
                _normalized_bytes(pm_path, rel),
                msg="Bundle drift detected for {}".format(rel.as_posix()),
            )


if __name__ == "__main__":
    unittest.main()
