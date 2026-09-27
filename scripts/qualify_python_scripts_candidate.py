"""Run native qualifications using an explicitly built payload, without installing it.

Run with glyphs-cli: ... this_file.py -- build/python-scripts-milestone workflow
The final argument is saved or saved-package.
"""
import importlib
import json
from pathlib import Path
import runpy
import sys
ROOT=Path(__file__).resolve().parents[1]
build=Path(sys.argv[-2]).resolve();suite=sys.argv[-1]
assert suite in ('saved','saved-package')
resources=build/'Glyphs MCP Bridge.glyphsPlugin/Contents/Resources'
sys.path[:0]=[str(build/'sidecar'),str(resources),str(ROOT/'scripts')]
loaded={}
for name in ('glyphs_mcp_protocol.script_targets','glyphs_mcp_bridge.core','glyphs_mcp_sidecar.service','glyphs_mcp_sidecar.native_worker'):
    module=importlib.import_module(name);path=Path(module.__file__).resolve()
    assert path.is_relative_to(build),(name,path)
    loaded[name]=str(path)
script=ROOT/'scripts/qualify_saved_scripts_native.py'
sys.argv=[str(script), 'glyphspackage' if suite=='saved-package' else 'glyphs']
runpy.run_path(str(script),run_name='__main__')
manifest=json.loads((build/'manifest.json').read_text())
result=dict(passed=True,suite=suite,loadedModules=loaded,bridge=manifest['bridge']['codeHash'],sidecar=manifest['sidecar']['codeHash'])
(ROOT/f'build/python-scripts-candidate-{suite}.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
