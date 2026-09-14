"""Read-only verification of the final receipt, payloads and managed skills."""
from pathlib import Path
from datetime import datetime, timezone
import gzip, hashlib, json, sys

OUT = Path(__file__).resolve().parent
S = OUT.parents[1]
sys.path.insert(0, str(S / 'scripts'))
from build_simple_v2 import _identity

receipt = json.loads((Path.home() / 'Library/Application Support/Glyphs MCP/lean-v2/installation.json').read_text())
manifest = json.loads((OUT / 'candidate-manifest.json').read_text())
checks = []
def check(name, expected, observed):
    checks.append(dict(name=name, expected=expected, observed=observed, passed=expected == observed))

for row in receipt['installed']:
    check(row['path'], row['identity'], _identity(Path(row['path'])))
for part in ('sidecar', 'bridge'):
    check(part + ' receipt versus candidate', manifest[part]['codeHash'], receipt[part]['codeHash'])

def load(name):
    p = OUT / name
    return json.loads(p.read_bytes() if p.exists() else gzip.decompress(p.with_suffix(p.suffix + '.gz').read_bytes()))

runtime = load('runtime-final.json')['data']
native = load('native-facts.json')
for part, actual in (('sidecar', runtime), ('bridge', runtime['bridge'])):
    check(part + ' running fingerprint', manifest[part]['codeHash'], actual['codeHash'])
    check(part + ' release metadata', manifest[part]['release'], actual['release'])
check('MCP initialization release', manifest['releaseVersion'], native['initialize']['serverInfo']['version'])
baseline_tools = load('baseline-catalog.json')[1]['response']['result']['tools']
check('unchanged seven public schemas', {t['name']: t['inputSchema'] for t in baseline_tools},
      {t['name']: t['inputSchema'] for t in native['catalog']['tools']})
check('unchanged bridge protocol', 1, runtime['bridge']['protocol'])
check('unchanged interface revision', 1, runtime['interfaceVersion'])
check('new capability negotiated', True, 'master.properties.v1' in runtime['readCapabilities'])
check('original open paths and dirty states',
      sorted((r['path'], r['dirty']) for r in load('documents-before.json')['data']),
      sorted((r['path'], r['dirty']) for r in load('documents-final.json')['data']))

def files(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()
            and not any(x.startswith('.') or x == '__pycache__' for x in p.relative_to(root).parts)
            and p.suffix != '.pyc'}

for row in json.loads((OUT / 'skills-install.json').read_text())['entries']:
    name = row['name']
    expected = files(S / 'skills' / name)
    installed = files(Path(row['path']))
    packaged = files(S / 'build/m7-master-properties-candidate-20260914/skills' / name)
    check(name + ' installed files', expected, installed)
    check(name + ' packaged files', expected, packaged)
    check(name + ' repository mirror', expected, files(S / 'plugins/glyphs-mcp/skills' / name))

result = dict(at=datetime.now(timezone.utc).isoformat(), receipt=receipt, checks=checks,
              passed=all(c['passed'] for c in checks))
(OUT / 'installed-verification.json').write_text(json.dumps(result, indent=2))
print(json.dumps(dict(passed=result['passed'], checks=len(checks), failures=[c['name'] for c in checks if not c['passed']]), indent=2))
assert result['passed']
