"""Deterministic installed-runtime and Codex-cache identity checks."""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/verify_v2_local_install.py"


class V2LocalInstallVerifierTests(unittest.TestCase):
    def test_exact_copies_pass_and_one_changed_file_fails(self) -> None:
        specification = importlib.util.spec_from_file_location(
            "verify_v2_local_install", SCRIPT
        )
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        runtime = (
            REPO
            / "build/installer-payload/Payload/Plugins/Glyphs4/Glyphs MCP.glyphsPlugin"
        )
        if not runtime.is_dir():
            self.skipTest("build the v2 runtime before local identity verification")
        temporary_root = REPO / ".tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="local-install-verifier-", dir=temporary_root
        ) as temporary:
            root = Path(temporary)
            installed = root / "Glyphs MCP.glyphsPlugin"
            cache = root / "cache"
            shutil.copytree(runtime, installed)
            shutil.copytree(REPO / "plugins/glyphs-mcp", cache)

            self.assertTrue(module.verify(installed, cache)["ok"])
            target = cache / "README.md"
            target.write_text(
                target.read_text(encoding="utf-8") + "\nchanged\n",
                encoding="utf-8",
            )
            report = module.verify(installed, cache)
            self.assertFalse(report["ok"])
            self.assertEqual(
                report["codexCacheMismatch"]["changed"], ["README.md"]
            )


if __name__ == "__main__":
    unittest.main()
