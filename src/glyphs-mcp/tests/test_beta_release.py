"""Beta artifacts must never become stable updates or stable downloads."""
import hashlib
import json
from pathlib import Path
import plistlib
import sys
import xml.etree.ElementTree as ET

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'scripts'))
from desktop_release_identity import identity, load
from prepare_desktop_update import feed, SPARKLE
from release_discovery import verify
from release_security import validate_release_metadata, validate_release_state, ReleaseSecurityError


def test_current_checkout_is_beta_5_build_47():
    release = load(REPO)
    assert release['version'] == '2.0.0'
    assert release['tag'] == 'v2.0.0-beta.5'
    assert release['label'] == '2.0.0 Beta 5'
    assert release['installerBuild'] == 47


def test_beta_5_validation_records_the_published_signed_release():
    text = (REPO / 'BETA5-VALIDATION.md').read_text()
    assert '`2.0.0-beta.5`' in text
    assert 'desktop build 47' in text
    assert 'published signed and notarized GitHub prerelease' in text
    assert 'https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.5' in text
    assert 'cadfadac6779eeb0e2051f1c0b8c2feba1010ef4a8f43709594729f732e4c9eb' in text
    assert '0756645c3675de7096761c07638d93bb1bc3d447fe89af9f34007c5d93c06fca' in text
    assert 'd7b02fe610e343d085dfe9afb542e6091e745519d5c193ef8bc3e66655dcda0d' in text


def test_beta_identity_preserves_numeric_bundle_version_and_build():
    release = identity('2.0.0', 'beta', 1)
    assert release['version'] == '2.0.0'
    assert release['tag'] == 'v2.0.0-beta.1'
    assert release['label'] == '2.0.0 Beta 1'
    assert release['branch'] != identity('2.0.0')['branch']
    for key in ('feedURL', 'registryURL'):
        assert '/lit/v2-beta/' in release[key]
        assert release[key] != identity('2.0.0')[key]


@pytest.mark.parametrize('channel,number', [('beta', 0), ('beta', -1), ('beta', True), ('stable', 1), ('rc', 1)])
def test_invalid_channel_configuration_is_rejected(channel, number):
    with pytest.raises(ValueError): identity('2.0.0', channel, number)


def test_beta_feed_uses_increasing_build_even_when_marketing_version_decreases():
    node = ET.fromstring(feed('2.0.0', 43, 'https://example.org/beta.zip', 'fixture', 100,
                             channel='beta', beta_number=1)).find('channel/item')
    assert int(node.findtext('{'+SPARKLE+'}version')) > 42
    assert node.findtext('{'+SPARKLE+'}shortVersionString') == '2.0.0 Beta 1'


def test_beta_metadata_rejects_stable_tag_app_channel_and_urls(tmp_path):
    source = tmp_path / 'src/bridge/glyphs_mcp_bridge/__init__.py'
    source.parent.mkdir(parents=True)
    source.write_text('PROJECT_VERSION = "2.0.0"\n')
    project = tmp_path / 'macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj'
    project.parent.mkdir(parents=True)
    project.write_text('MARKETING_VERSION = 2.0.0;\nCURRENT_PROJECT_VERSION = 43;\n')
    (tmp_path / 'release.json').write_text('{"channel":"beta","betaNumber":1}')
    release = load(tmp_path)
    info = {'CFBundleShortVersionString': '2.0.0', 'CFBundleVersion': '43',
            'GMCPReleaseChannel': 'beta', 'GMCPBetaNumber': 1,
            'SUFeedURL': release['feedURL'], 'GMCPTemplateRegistryURL': release['registryURL']}
    app = tmp_path / 'Info.plist'
    app.write_bytes(plistlib.dumps(info))
    assert validate_release_metadata(tmp_path, release['tag'], app) == '2.0.0'
    with pytest.raises(ReleaseSecurityError): validate_release_metadata(tmp_path, 'v2.0.0', app)
    for key, wrong in [('CFBundleVersion', '42'), ('GMCPReleaseChannel', 'stable'),
                       ('GMCPBetaNumber', 2), ('SUFeedURL', identity('2.0.0')['feedURL']),
                       ('GMCPTemplateRegistryURL', identity('2.0.0')['registryURL'])]:
        app.write_bytes(plistlib.dumps({**info, key: wrong}))
        with pytest.raises(ReleaseSecurityError): validate_release_metadata(tmp_path, release['tag'], app)


def test_beta_upload_requires_prerelease_and_rejects_latest_alias(tmp_path):
    tag = 'v2.0.0-beta.1'
    state = {'tagName': tag, 'isDraft': True, 'assets': [], 'isPrerelease': True}
    validate_release_state(state, tag, ['Glyphs-MCP-2.0.0-beta.1.dmg'])
    with pytest.raises(ReleaseSecurityError): validate_release_state({**state, 'isPrerelease': False}, tag, [])
    asset = tmp_path / 'Glyphs-MCP-2.0.0-beta.1.dmg'
    asset.write_bytes(b'fixture')
    release = {'tag_name': tag, 'draft': False, 'prerelease': True,
               'html_url': 'https://github.com/thierryc/Glyphs-mcp/releases/tag/' + tag,
               'assets': [{'name': asset.name, 'size': asset.stat().st_size, 'state': 'uploaded',
                           'digest': 'sha256:' + hashlib.sha256(asset.read_bytes()).hexdigest(),
                           'browser_download_url': 'https://github.com/thierryc/Glyphs-mcp/releases/download/' + tag + '/' + asset.name}]}
    assert verify(release, tag, [asset], published=True)['published']
    with pytest.raises(ValueError): verify({**release, 'prerelease': False}, tag, [asset], published=True)
    latest = tmp_path / 'Glyphs-MCP-latest.dmg'
    latest.write_bytes(asset.read_bytes())
    with pytest.raises(ValueError, match='[Ll]atest'): verify(release, tag, [latest], published=True)


def test_dmg_layout_targets_window_and_verifies_persisted_positions():
    script = (REPO / 'scripts/make_installer_dmg.sh').read_text()
    assert 'set position of item appName of dmgWindow to {170, 194}' in script
    assert 'set position of item "Applications" of dmgWindow to {510, 194}' in script
    assert 'set position of item appName of mountedFolder' not in script
    assert 'set appPosition to position of item appName of verifiedWindow' in script
    assert 'set applicationsPosition to position of item "Applications" of verifiedWindow' in script
    assert 'if appPosition is not equal to {170, 194}' in script
    assert 'if applicationsPosition is not equal to {510, 194}' in script
    assert 'background.tiff' in script
    assert 'background@2x.png' in script
    renderer = (REPO / 'scripts/render_dmg_background.sh').read_text()
    assert 'render_representation 1' in renderer
    assert 'render_representation 2' in renderer
    assert 'tiffutil -cathidpicheck' in renderer
