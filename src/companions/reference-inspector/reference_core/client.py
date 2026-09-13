"""Background subprocess launcher and bounded reference-geometry cache."""

import json
import os
import shutil
import subprocess
import tempfile
from collections import OrderedDict
from pathlib import Path


class ReferenceReader:
    def __init__(self, application):
        self.application = application
        self.root = Path(tempfile.mkdtemp(prefix="glyphs-reference-"))
        self.cache = OrderedDict()
        self.references = OrderedDict()

    def read(self, request):
        key = json.dumps(request, sort_keys=True)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        executable = (os.environ.get("GLYPHS_MCP_GLYPHS_CLI") or shutil.which("glyphs")
                      or "/Library/Frameworks/Python.framework/Versions/Current/bin/glyphs")
        receipt = Path.home() / "Library/Application Support/Glyphs MCP/lean-v2/installation.json"
        if receipt.is_file():
            managed = json.loads(receipt.read_text()).get("glyphsCLI")
            if managed and Path(managed).is_file():
                executable = managed
        resource_root = str(Path(__file__).resolve().parent.parent)
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        environment["PYTHONPATH"] = os.pathsep.join([resource_root, environment.get("PYTHONPATH", "")])
        context = json.dumps({key: request.get(key) for key in ("source", "reference", "epoch")}, sort_keys=True)
        pinned = self.references.get(context)
        payload = {**request, "cache": str(self.root / "sources"), "output": str(self.root / "result.json")}
        if pinned:
            payload.update(reference={"kind": "file", "source": pinned["path"]}, refresh=False)
        request_file = self.root / "request.json"
        request_file.write_text(json.dumps(payload))
        command = [executable, "run", "--quiet", "--app", self.application,
                   "--plugins", "", "-m", "reference_core.native_worker", "--", str(request_file)]
        process = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, env=environment, timeout=90)
        if process.returncode:
            raise ValueError(process.stderr.decode(errors="replace")[-1000:] or "The reference reader could not start")
        result = json.loads((self.root / "result.json").read_text())
        if not result.get("ok"):
            raise ValueError(result.get("error") or "Reference unavailable")
        data = result["data"]
        if pinned:
            data.update(pinned)
        else:
            self.references[context] = {name: data[name] for name in ("path", "identity", "label", "commit")}
            while len(self.references) > 16:
                self.references.popitem(last=False)
        self.cache[key] = data
        while len(self.cache) > 16:
            self.cache.popitem(last=False)
        return result["data"]
