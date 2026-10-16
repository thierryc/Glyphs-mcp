#!/usr/bin/env python3
"""Qualify desktop package copies using disposable fonts and an explicit Glyphs app."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
V4 = '''{
.formatVersion = 4;
familyName = "Package Copy Quartic Fixture";
fontMaster = ({id = m01; name = Regular;});
glyphs = ({glyphname = A; unicode = "0041"; layers = ({
layerId = m01; width = 600;
shapes = (
{groupId = testGroup; attr = {opacity = 0.7;};},
{attr = {group = testGroup;}; closed = 1;
nodes = ((0,0,l),(10,40,o),(30,60,o),(50,40,o),(60,0,u));}
);
});});
unitsPerEm = 1000;
}'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True)
    parser.add_argument("--cli", type=Path, default=ROOT / "build/private-runtime/arm64/bin/glyphs")
    parser.add_argument("--sidecar", type=Path, default=ROOT / "src/sidecar")
    args = parser.parse_args()
    fixtures = ROOT / "skills/glyphs-mcp-development/assets/knowledge/docs/sdk/GlyphsFileFormat"
    worker = args.sidecar / "glyphs_mcp_sidecar/package_copy.py"
    report = []
    with tempfile.TemporaryDirectory(prefix="glyphs-package-qualification-") as temporary:
        root = Path(temporary)
        shutil.copytree(fixtures / "files", root / "files")
        for label in ("legacy", "v3", "v4-quartic-group", "malformed"):
            source = root / ("Temporary Font é " + label + ".glyphs")
            if label == "v4-quartic-group": source.write_text(V4)
            elif label == "malformed": source.write_text("not a font")
            else: shutil.copy2(fixtures / ("GlyphsFileFormatv2.glyphs" if label == "legacy" else "GlyphsFileFormatv3.glyphs"), source)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            destination = source.with_suffix(".glyphspackage")
            request, output = root / "request.json", root / "result.json"
            output.unlink(missing_ok=True)
            request.write_text(json.dumps({"source":str(source), "destination":str(destination),
                "cli":str(args.cli.resolve()), "application":args.app, "result":str(output)}))
            execution = subprocess.run([sys.executable, "-B", str(worker), str(request)],
                env={**os.environ, "PYTHONPATH":str(ROOT / "src/protocol"), "PYTHONDONTWRITEBYTECODE":"1"},
                capture_output=True, text=True, timeout=320)
            result = json.loads(output.read_text()) if output.exists() else {"error":execution.stderr}
            assert hashlib.sha256(source.read_bytes()).hexdigest() == before, label
            if label == "malformed":
                assert not result["ok"] and not destination.exists(), result
            else:
                assert execution.returncode == 0 and result["ok"], result
                assert (destination / "fontinfo.plist").is_file()
                if label == "v4-quartic-group":
                    content = (destination / "glyphs/A_.glyph").read_text()
                    assert "testGroup" in content and ",u)" in content.replace("\n", "").replace(" ", ""), content
            assert not list(root.glob(".glyphs-package-copy-*")), label
            report.append({"fixture":label, "passed":True, "originalUnchanged":True,
                           "verification":result.get("data")})
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
