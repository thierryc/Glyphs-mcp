"""Plugin-free qualification of production new-font construction and serialization."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for component in ('protocol', 'bridge'):
    sys.path.insert(0, str(ROOT / 'src' / component))
from GlyphsApp import GSFont
from glyphs_mcp_bridge.core import BridgeError
from glyphs_mcp_bridge.document_creation import construct
from glyphs_mcp_protocol.document_creation import options

out = ROOT / 'reports/document-creation-20260930'
checks = []
for suffix in ('.glyphs', '.glyphspackage'):
    target = out / ('Detached qualification verified' + suffix)
    if target.exists():
        raise RuntimeError('Qualification destination already exists: ' + str(target))
    font, masters, instances = construct(options('MCP Creation Qualification', 'detached' + suffix, 2048), {}, BridgeError)
    assert font.familyName == 'MCP Creation Qualification' and font.upm == 2048
    assert len(font.glyphs) == 0 and len(font.masters) == len(font.instances) == 1
    assert font.masters[0].name == font.instances[0].name == 'Regular'
    assert len(masters) == len(instances) == 1
    font.save(str(target))
    # Bypass LaunchServices type lookup in the plugin-free worker, using the
    # native reader directly. The earlier package probe records that distinction.
    from Foundation import NSURL
    reopened, error = GSFont.alloc().initWithURL_error_(NSURL.fileURLWithPath_(str(target)), None)
    assert reopened is not None and error is None
    assert reopened.familyName == font.familyName and reopened.upm == 2048
    assert len(reopened.masters) == len(reopened.instances) == 1
    checks.append({'format': suffix, 'masterIds': masters, 'instanceIds': instances, 'reopenVerified': True})
report = {'checks': checks, 'scope': 'detached production constructor and native serialization; live MCP document opening and NSDocument Save As unverified'}
(out / 'detached-native.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
