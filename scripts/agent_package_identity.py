"""Deterministic identity for the packaged agent instructions, not a client receipt."""
import importlib.util
import json
from pathlib import Path
from desktop_release_identity import load


def record(root):
    root = Path(root)
    package = root / 'plugins/glyphs-mcp'
    version = json.loads((package / '.codex-plugin/plugin.json').read_text())['version']
    release = load(root)
    if version != release['version']:
        raise ValueError('Agent plugin and product versions disagree')
    spec = importlib.util.spec_from_file_location('agent_payload_identity', root / 'src/protocol/glyphs_mcp_protocol/identity.py')
    identity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(identity)
    return dict(schemaVersion=1, name='glyphs-mcp', version=version,
                releaseVersion=release['releaseVersion'], skillsDigest=identity.payload_hash(package / 'skills'))


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    path = root / 'plugins/glyphs-mcp/glyphs-mcp-agent.json'
    path.write_text(json.dumps(record(root), sort_keys=True, indent=2) + '\n')
