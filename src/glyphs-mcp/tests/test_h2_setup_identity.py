"""Keep current setup claims tied to the shipped release and inventory sources."""
import importlib.util
import json
from pathlib import Path
import plistlib
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'scripts'))
from desktop_release_identity import load


def test_identity_table_matches_release_source_protocol_and_inventory():
    release = load(ROOT)
    text = (ROOT/'content/reference/version-identity.mdx').read_text()
    values = dict(re.findall(r'^\| ([^|]+?) \| `([^`]+)` \|$', text, re.M))
    protocol_spec = importlib.util.spec_from_file_location('h2_protocol', ROOT/'src/protocol/glyphs_mcp_protocol/models.py')
    protocol = importlib.util.module_from_spec(protocol_spec)
    protocol_spec.loader.exec_module(protocol)
    manifest = json.loads((ROOT/'skills/manifest.json').read_text())
    with (ROOT/'src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Info.plist').open('rb') as f:
        legacy = plistlib.load(f)
    expected = {'Product version':release['version'], 'Release version':release['releaseVersion'],
                'Channel':release['channel'], 'Beta number':str(release['betaNumber']),
                'Installer build':str(release['installerBuild']),
                'Lean interface':'glyphs-mcp-sidecar', 'Interface revision':'1',
                'Bridge protocol':str(protocol.PROTOCOL_VERSION),
                'Managed skills':str(len(manifest['managedSkills'])),
                'MCP tools':str(len(protocol.TOOL_NAMES)), 'Job kinds':'5',
                'Desktop payload targets':'Glyphs 4 only',
                'Separate pinned v1 release':legacy['CFBundleShortVersionString']}
    assert values == expected
    assert release['feedURL'] in text and release['tag'] in text
    for extension in ('dmg','zip'):
        assert f"Glyphs-MCP-{release['releaseVersion']}.{extension}" in text


def test_user_skill_table_exactly_matches_the_current_manifest():
    text = (ROOT/'content/getting-started/use-agent-skills.mdx').read_text()
    names = re.findall(r'^\| `(glyphs[^`]*)` \|', text, re.M)
    manifest = json.loads((ROOT/'skills/manifest.json').read_text())
    assert names == [item['name'] for item in manifest['managedSkills']]


def test_current_migration_and_packaging_do_not_reintroduce_retired_identity():
    names = ['content/getting-started/migrate-from-v1.mdx',
             'content/getting-started/installation.mdx', 'content/reference/settings.mdx',
             'content/contributor/release-build-notes.mdx', 'macos-installer/README.md',
             'macos-installer/RELEASING.md']
    for name in names:
        text = (ROOT/name).read_text()
        assert not re.search(r'(?:bridge|protocol)[^\n.]*\(?0\.1\.0', text, re.I), name
        assert '2.0.0 (0.1.0)' not in text and 'Signed local candidate' not in text, name
        assert 'ten managed skills' not in text, name
    release = load(ROOT)
    for name in ['content/contributor/release-build-notes.mdx','macos-installer/RELEASING.md']:
        assert release['feedURL'] in (ROOT/name).read_text()


def test_release_skill_reference_is_local_synchronized_and_matches_release():
    root = ROOT/'skills/glyphs-mcp-release'
    entry = (root/'SKILL.md').read_text()
    target = 'references/release-identity.md'
    assert f']({target})' in entry
    assert 'blob/main/content/' not in entry
    text = (root/target).read_text()
    release = load(ROOT)
    assert release['releaseVersion'] in text and release['feedURL'] in text
    assert f"build **{release['installerBuild']}**" in text
    mirror = ROOT/'plugins/glyphs-mcp/skills/glyphs-mcp-release'
    for p in root.rglob('*'):
        if p.is_file():
            assert p.read_bytes() == (mirror/p.relative_to(root)).read_bytes()


def test_desktop_copy_uses_existing_release_label_and_real_backup_location():
    text = (ROOT/'macos-installer/GlyphsMCPInstaller/Sources/ContentView.swift').read_text()
    welcome = text.split('struct DesktopWelcomeView:',1)[1]
    assert 'Text(DesktopIdentity.versionLabel)' in welcome
    assert '(bridge 0.1.0)' not in text and '(0.1.0)' not in welcome
    model = (ROOT/'macos-installer/GlyphsMCPInstaller/Sources/InstallerViewModel.swift').read_text()
    assert 'beside their original paths' not in model
    assert 'Modified or unowned skills were preserved' in model
