#!/usr/bin/env python3
"""Sign the bundled development engine and refresh only its release-copy hashes."""
import argparse
import hashlib
import json
from pathlib import Path

from release_payload import IDENTITY, run, verify_code
from verify_desktop_app import validate_embedded_beztrace


def sign(app, identity=IDENTITY):
    validate_embedded_beztrace(app)
    root = Path(app) / 'Contents/Resources/Beztrace/beztrace-0.1.1-dev.4'
    engine = root / 'bin/beztrace'
    run('/usr/bin/codesign', '--force', '--sign', identity, '--timestamp', '--options', 'runtime', engine)
    verify_code(engine, identity)
    manifest_path = root / 'development-engine.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['developerIDSigning'] = 'signed-in-glyphs-mcp-release'
    manifest['notarization'] = 'submitted-with-host-app'
    manifest['files']['bin/beztrace'] = hashlib.sha256(engine.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    files = sorted(path for path in root.rglob('*') if path.is_file() and path.name != 'SHA256SUMS')
    (root / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.relative_to(root).as_posix() + '\n'
        for path in files))
    return validate_embedded_beztrace(app)


def verify(app, identity=IDENTITY):
    result = validate_embedded_beztrace(app)
    verify_code(Path(app) / 'Contents/Resources/Beztrace/beztrace-0.1.1-dev.4/bin/beztrace', identity)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('sign', 'verify'))
    parser.add_argument('app', type=Path)
    parser.add_argument('--identity', default=IDENTITY)
    args = parser.parse_args()
    print(json.dumps((sign if args.action == 'sign' else verify)(args.app, args.identity), indent=2))
