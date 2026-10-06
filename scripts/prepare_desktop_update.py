#!/usr/bin/env python3
"""Create and verify a local Sparkle update candidate; never publish it."""
import argparse
from desktop_release_identity import identity
import hashlib
import json
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from prepare_desktop_dependencies import prepare
from release_payload import verify_code

SPARKLE = 'http://www.andymatuschak.org/xml-namespaces/sparkle'
ET.register_namespace('sparkle', SPARKLE)


def feed(version, build, url, signature, size, *, channel="stable", beta_number=0):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or not str(build).isdigit(): raise ValueError('Invalid desktop version')
    release = identity(version, channel, beta_number)
    root = ET.Element('rss', {'version': '2.0'})
    channel = ET.SubElement(root, 'channel')
    ET.SubElement(channel, 'title').text = 'Glyphs MCP Desktop'
    ET.SubElement(channel, 'link').text = 'https://github.com/thierryc/Glyphs-mcp'
    item = ET.SubElement(channel, 'item')
    ET.SubElement(item, 'title').text = 'Glyphs MCP ' + release['label']
    ET.SubElement(item, '{'+SPARKLE+'}version').text = str(build)
    ET.SubElement(item, '{'+SPARKLE+'}shortVersionString').text = release['label']
    ET.SubElement(item, '{'+SPARKLE+'}minimumSystemVersion').text = '14.0'
    ET.SubElement(item, 'description').text = 'The desktop application manages components, sidecar activity and local font projects. Component migration is a separate installation step.'
    ET.SubElement(item, 'enclosure', {'url': url, '{'+SPARKLE+'}edSignature': signature, 'length': str(size), 'type': 'application/octet-stream'})
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True) + b'\n'


def candidate(app, output):
    app, output = app.resolve(), output.resolve()
    info = plistlib.loads((app/'Contents/Info.plist').read_bytes())
    if info['CFBundleIdentifier'] != 'cx.ap.glyphsMcp': raise ValueError('Not a Glyphs MCP desktop application')
    version, build = info['CFBundleShortVersionString'], info['CFBundleVersion']
    release = identity(version, info.get('GMCPReleaseChannel', 'stable'), info.get('GMCPBetaNumber', 0))
    if info.get('SUFeedURL') != release['feedURL']:
        raise ValueError('App must use its release channel update feed')
    verify_code(app)
    subprocess.run(['/usr/bin/xcrun','stapler','validate',str(app)],check=True)
    dependencies = prepare()
    public_key = subprocess.check_output([str(dependencies/'bin/generate_keys'),'--account','cx.ap.glyphsMcp','-p'],text=True).strip()
    if public_key != info.get('SUPublicEDKey'): raise ValueError('The update signing key does not match the application')
    output.mkdir(parents=True, exist_ok=True)
    archive = output/('Glyphs-MCP-'+release['releaseVersion']+'.zip')
    subprocess.run(['/usr/bin/ditto','-c','-k','--keepParent',str(app),str(archive)],check=True)
    signer = str(dependencies/'bin/sign_update')
    signature = subprocess.check_output([signer,'--account','cx.ap.glyphsMcp','-p',str(archive)],text=True).strip()
    subprocess.run([signer,'--account','cx.ap.glyphsMcp','--verify',str(archive),signature],check=True)
    appcast = output/'appcast.xml'
    appcast.write_bytes(feed(version, build, 'https://github.com/thierryc/Glyphs-mcp/releases/download/'+release['tag']+'/'+archive.name,
                            signature,archive.stat().st_size,channel=release['channel'],beta_number=release['betaNumber']))
    subprocess.run([signer,'--account','cx.ap.glyphsMcp',str(appcast)],check=True)
    subprocess.run([signer,'--account','cx.ap.glyphsMcp','--verify',str(appcast)],check=True)
    checksums = {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in (archive, appcast)}
    (output/'SHA256SUMS').write_text(''.join(digest+'  '+name+'\n' for name,digest in sorted(checksums.items())))
    result = {'releaseVersion':release['releaseVersion'],'channel':release['channel'],'tag':release['tag'],'version':version,'build':build,'bundleIdentifier':info['CFBundleIdentifier'], 'publicKey':public_key,
              'archive':archive.name,'signature':signature,'checksums':checksums,'published':False}
    (output/'update-candidate.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def verify_metadata(app, output):
    """Fail closed on missing assets or mismatched feed/candidate identity."""
    info = plistlib.loads((app/'Contents/Info.plist').read_bytes())
    release = identity(info['CFBundleShortVersionString'], info.get('GMCPReleaseChannel', 'stable'),
                       info.get('GMCPBetaNumber', 0))
    if info.get('CFBundleIdentifier') != 'cx.ap.glyphsMcp' or info.get('SUFeedURL') != release['feedURL']:
        raise ValueError('Update app identity/feed mismatch')
    archive = output/('Glyphs-MCP-'+release['releaseVersion']+'.zip')
    appcast = output/'appcast.xml'
    for path in (archive, appcast, output/'update-candidate.json'):
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing regular update asset: '+str(path))
    record = json.loads((output/'update-candidate.json').read_text())
    items = ET.fromstring(appcast.read_bytes()).findall('channel/item')
    if len(items) != 1:
        raise ValueError('Expected one update candidate')
    item = items[0]
    enclosures = item.findall('enclosure')
    if len(enclosures) != 1:
        raise ValueError('Expected one update enclosure')
    enclosure = enclosures[0]
    url = 'https://github.com/thierryc/Glyphs-mcp/releases/download/'+release['tag']+'/'+archive.name
    signature = enclosure.get('{'+SPARKLE+'}edSignature')
    if (enclosure.get('url') != url or enclosure.get('length') != str(archive.stat().st_size)
            or not signature or enclosure.get('type') != 'application/octet-stream'
            or item.findtext('{'+SPARKLE+'}version') != str(info['CFBundleVersion'])
            or item.findtext('{'+SPARKLE+'}shortVersionString') != release['label']
            or item.findtext('{'+SPARKLE+'}minimumSystemVersion') != '14.0'):
        raise ValueError('Update enclosure/version mismatch')
    expected = {'releaseVersion':release['releaseVersion'], 'channel':release['channel'],
                'tag':release['tag'], 'version':release['version'], 'build':info['CFBundleVersion'],
                'bundleIdentifier':info['CFBundleIdentifier'], 'publicKey':info.get('SUPublicEDKey'),
                'archive':archive.name, 'signature':signature, 'published':False,
                'checksums':{path.name:hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in (archive, appcast)}}
    if any(record.get(key) != value for key,value in expected.items()):
        raise ValueError('Update candidate metadata/checksum mismatch')
    return archive, appcast, signature, expected


def verify_candidate(app, output):
    app, output = app.resolve(), output.resolve()
    archive, appcast, signature, record = verify_metadata(app, output)
    dependencies = prepare()
    signer = str(dependencies/'bin/sign_update')
    public_key = subprocess.check_output([str(dependencies/'bin/generate_keys'), '--account',
                                          'cx.ap.glyphsMcp', '-p'], text=True).strip()
    if public_key != record['publicKey']:
        raise ValueError('The update signing key does not match the application')
    subprocess.run([signer,'--account','cx.ap.glyphsMcp','--verify',str(archive),signature],check=True)
    subprocess.run([signer,'--account','cx.ap.glyphsMcp','--verify',str(appcast)],check=True)
    from verify_desktop_app import tree_digest
    with tempfile.TemporaryDirectory(prefix='glyphs-update-verify-') as temporary:
        subprocess.run(['/usr/bin/ditto','-x','-k',str(archive),temporary],check=True)
        extracted = Path(temporary)/app.name
        if not extracted.is_dir() or tree_digest(extracted) != tree_digest(app):
            raise ValueError('Sparkle ZIP does not contain the exact release app')
        verify_code(extracted)
        subprocess.run(['/usr/bin/xcrun','stapler','validate',str(extracted)],check=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true'); parser.add_argument('--app',required=True,type=Path); parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args(); print(json.dumps((verify_candidate if args.verify else candidate)(args.app,args.output),sort_keys=True))
