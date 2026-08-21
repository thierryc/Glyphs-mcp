"""Target-aware installer payload contract tests for Glyphs MCP 2.0."""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
BUILDER = REPO / "scripts" / "build_installer_payload.py"
PLUGIN = "Glyphs MCP.glyphsPlugin"


def _file_map(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class V2InstallerPayloadTests(unittest.TestCase):
    def _build(self, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(BUILDER), "--output-root", str(output)],
            cwd=REPO,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )

    def test_builder_assembles_deterministic_target_aware_payload(self) -> None:
        temporary_root = REPO / ".tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="installer-payload-", dir=temporary_root) as tmp:
            first = Path(tmp) / "first" / "Payload"
            second = Path(tmp) / "second" / "Payload"
            for output in (first, second):
                result = self._build(output)
                self.assertEqual(result.returncode, 0, msg=result.stderr)

            self.assertEqual(_file_map(first), _file_map(second))
            manifest = json.loads((first / "payload.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schemaVersion"], 2)
            self.assertEqual(set(manifest["targets"]), {"3", "4"})

            glyphs3 = manifest["targets"]["3"]
            glyphs4 = manifest["targets"]["4"]
            self.assertEqual(glyphs3["runtimeTrack"], "1.x")
            self.assertEqual(glyphs3["updatePolicy"], "pinned")
            self.assertEqual(glyphs3["pluginVersion"], "1.11.0")
            self.assertEqual(glyphs3["baseline"]["tag"], "v1.11.0")
            self.assertEqual(glyphs3["baseline"]["commit"], "13ca805")
            self.assertEqual(glyphs4["runtimeTrack"], "2.x")
            self.assertEqual(glyphs4["updatePolicy"], "release")

            for target in (glyphs3, glyphs4):
                plugin = first / target["pluginPath"]
                self.assertTrue((plugin / "Contents/MacOS/plugin").is_file())
                with (plugin / "Contents/Info.plist").open("rb") as stream:
                    info = plistlib.load(stream)
                self.assertEqual(info["CFBundleShortVersionString"], target["pluginVersion"])
                self.assertEqual(info["productPageURL"], "https://github.com/thierryc/Glyphs-mcp")
                serialized = json.dumps(info, sort_keys=True)
                self.assertNotIn("____", serialized)

            resources4 = first / glyphs4["pluginPath"] / "Contents/Resources"
            self.assertTrue((resources4 / "glyphs_mcp_v2/runtime.py").is_file())
            self.assertIn(
                "from glyphs_mcp_v2.runtime import create_glyphs_server",
                (resources4 / "mcp_tools.py").read_text(encoding="utf-8"),
            )
            resources3 = first / glyphs3["pluginPath"] / "Contents/Resources"
            self.assertFalse((resources3 / "glyphs_mcp_v2").exists())

    def test_builder_rejects_output_outside_worktree(self) -> None:
        result = self._build(Path("/private/tmp/glyphs-mcp-installer-payload-escape"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must remain inside", result.stderr)


if __name__ == "__main__":
    unittest.main()
