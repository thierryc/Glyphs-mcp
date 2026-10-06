"""Offline update-asset fixtures; no signing, uploading, or runtime installation."""
import hashlib
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO/'scripts'))
import prepare_desktop_update as updates
from desktop_release_identity import identity
from release_asset_inventory import assets


def fixture(root, channel):
    release = identity('2.0.0', channel, 12 if channel == 'beta' else 0)
    app = root/'Glyphs MCP.app'
    (app/'Contents').mkdir(parents=True)
    info = {'CFBundleIdentifier':'cx.ap.glyphsMcp', 'CFBundleShortVersionString':'2.0.0',
            'CFBundleVersion':'54', 'GMCPReleaseChannel':channel, 'GMCPBetaNumber':release['betaNumber'],
            'SUFeedURL':release['feedURL'], 'SUPublicEDKey':'fixture-key'}
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    output = root/'updates';output.mkdir()
    archive = output/f"Glyphs-MCP-{release['releaseVersion']}.zip"
    with zipfile.ZipFile(archive,'w') as zipped:
        zipped.write(app/'Contents/Info.plist', 'Glyphs MCP.app/Contents/Info.plist')
    appcast = output/'appcast.xml'
    appcast.write_bytes(updates.feed('2.0.0',54,
        f"https://github.com/thierryc/Glyphs-mcp/releases/download/{release['tag']}/{archive.name}",
        'fixture-signature',archive.stat().st_size,channel=channel,beta_number=release['betaNumber']))
    record = {'releaseVersion':release['releaseVersion'], 'channel':channel, 'tag':release['tag'],
              'version':'2.0.0','build':'54','bundleIdentifier':info['CFBundleIdentifier'],
              'publicKey':'fixture-key','archive':archive.name,'signature':'fixture-signature',
              'published':False, 'checksums':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                            for p in (archive,appcast)}}
    (output/'update-candidate.json').write_text(json.dumps(record))
    return app,output,archive,appcast


@pytest.mark.parametrize('channel', ['stable','beta'])
def test_upload_inventory_and_checksums_include_exact_update_assets(tmp_path,channel):
    release=identity('2.0.0',channel,12 if channel=='beta' else 0)
    checked=assets(tmp_path,release)
    uploaded=assets(tmp_path,release,include_manifest=True)
    assert uploaded==checked+[tmp_path/'dist/SHA256SUMS']
    assert tmp_path/f"dist/desktop-update/Glyphs-MCP-{release['releaseVersion']}.zip" in checked
    assert tmp_path/'dist/desktop-update/appcast.xml' in checked
    assert (tmp_path/'dist/Glyphs-MCP-latest.dmg' in checked)==(channel=='stable')
    assert (tmp_path/'dist/installer-app/Glyphs MCP.zip' in checked)==(channel=='stable')
    assert len(set(p.name for p in uploaded))==len(uploaded)


@pytest.mark.parametrize('channel', ['stable','beta'])
def test_coherent_update_metadata_passes(tmp_path,channel):
    app,output,archive,appcast=fixture(tmp_path,channel)
    result=updates.verify_metadata(app,output)
    assert result[:2]==(archive,appcast)


@pytest.mark.parametrize('channel', ['stable','beta'])
@pytest.mark.parametrize('missing', ['archive','appcast','update-candidate.json'])
def test_missing_update_assets_fail_closed(tmp_path,channel,missing):
    app,output,archive,appcast=fixture(tmp_path,channel)
    {'archive':archive,'appcast':appcast,'update-candidate.json':output/'update-candidate.json'}[missing].unlink()
    with pytest.raises(ValueError,match='Missing regular'):updates.verify_metadata(app,output)


@pytest.mark.parametrize('channel', ['stable','beta'])
@pytest.mark.parametrize('tamper', ['url','size','signature','build','channel','archive','key','checksum'])
def test_mismatched_candidate_or_feed_fails_closed(tmp_path,channel,tamper):
    app,output,archive,appcast=fixture(tmp_path,channel)
    record_path=output/'update-candidate.json';record=json.loads(record_path.read_text())
    if tamper in ('url','size','signature','build'):
        tree=ET.fromstring(appcast.read_bytes());item=tree.find('channel/item');enclosure=item.find('enclosure')
        if tamper=='url':enclosure.set('url','https://example.org/other.zip')
        elif tamper=='size':enclosure.set('length','0')
        elif tamper=='signature':enclosure.set('{'+updates.SPARKLE+'}edSignature','other')
        else:item.find('{'+updates.SPARKLE+'}version').text='53'
        appcast.write_bytes(ET.tostring(tree))
    elif tamper=='checksum':archive.write_bytes(archive.read_bytes()+b'corruption')
    else:record[{'channel':'channel','archive':'archive','key':'publicKey'}[tamper]]='wrong'
    record_path.write_text(json.dumps(record))
    with pytest.raises(ValueError):updates.verify_metadata(app,output)


@pytest.mark.parametrize('channel', ['stable','beta'])
def test_wrong_application_feed_rejected(tmp_path,channel):
    app,output,_,_=fixture(tmp_path,channel)
    plist=app/'Contents/Info.plist';info=plistlib.loads(plist.read_bytes())
    info['SUFeedURL']='https://example.org/wrong';plist.write_bytes(plistlib.dumps(info))
    with pytest.raises(ValueError,match='identity/feed'):updates.verify_metadata(app,output)


def mock_crypto(monkeypatch,tmp_path):
    # Test the verification route, not real Sparkle cryptography.
    monkeypatch.setattr(updates,'prepare',lambda:tmp_path)
    monkeypatch.setattr(updates.subprocess,'check_output',lambda *a,**k:'fixture-key')
    monkeypatch.setattr(updates,'verify_code',lambda _:None)
    real_run=subprocess.run
    def run(command,**kwargs):
        if command[0]=='/usr/bin/ditto':return real_run(command,**kwargs)
        return subprocess.CompletedProcess(command,0)
    monkeypatch.setattr(updates.subprocess,'run',run)


@pytest.mark.parametrize('channel', ['stable','beta'])
def test_archive_contains_exact_app_after_signature_verification(tmp_path,monkeypatch,channel):
    app,output,_,_=fixture(tmp_path,channel);mock_crypto(monkeypatch,tmp_path)
    assert updates.verify_candidate(app,output)['channel']==channel
    (app/'Contents/extra.txt').write_text('different release app')
    with pytest.raises(ValueError,match='exact release app'):updates.verify_candidate(app,output)


def test_invalid_signature_aborts_before_extraction(tmp_path,monkeypatch):
    app,output,_,_=fixture(tmp_path,'stable');mock_crypto(monkeypatch,tmp_path)
    commands=[]
    def reject(command,**kwargs):
        commands.append(command)
        raise subprocess.CalledProcessError(1,command)
    monkeypatch.setattr(updates.subprocess,'run',reject)
    with pytest.raises(subprocess.CalledProcessError):updates.verify_candidate(app,output)
    assert len(commands)==1 and '--verify' in commands[0]


def test_release_scripts_use_shared_inventory_and_verify_updates():
    publisher=(REPO/'scripts/publish_release_assets.sh').read_text()
    verifier=(REPO/'scripts/verify_release_artifacts.sh').read_text()
    assert 'release_asset_inventory.py' in publisher and '--include-manifest' in publisher
    assert 'release_asset_inventory.py' in verifier
    assert 'prepare_desktop_update.py" --verify' in verifier
    preparation=publisher[publisher.index('if [[ "$skip_build"'):publisher.index('verify_args=')]
    assert 'prepare_desktop_update.py' in preparation
    assert 'release_channel' not in preparation
