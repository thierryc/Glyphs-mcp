#!/usr/bin/env python3
"""Sign Sparkle's nested helpers inside out, preserving their sandbox entitlements."""
import argparse
from pathlib import Path
import subprocess
from release_payload import inventory, verify_code, IDENTITY, run


def sign(root, identity):
    root = Path(root).resolve()
    native, frameworks = inventory(root)
    bundles = frameworks + [path for path in root.rglob('*') if path.is_dir() and not path.is_symlink() and path.suffix in ('.app', '.xpc')]
    if not (root/'Sparkle.framework').is_dir(): raise ValueError('Sparkle is missing')
    for path in native + sorted(bundles, key=lambda path: (-len(path.parts), str(path))):
        # Sparkle ships sandboxed XPC services. Preserve these existing
        # entitlements while changing the signing team to the application's.
        run('/usr/bin/codesign', '--force', '--sign', identity, '--timestamp', '--options', 'runtime',
            '--preserve-metadata=identifier,entitlements', path)
        verify_code(path, identity)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('root', type=Path)
    parser.add_argument('--identity', default=IDENTITY); args = parser.parse_args()
    sign(args.root, args.identity)
