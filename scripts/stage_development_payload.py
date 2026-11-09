#!/usr/bin/env python3
"""Content-verified payload reuse for explicit unsigned development builds only."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from build_installer_payload import build_payload, validate_payload

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ('src/bridge', 'src/protocol', 'src/sidecar', 'src/companions',
          'skills', 'plugins/glyphs-mcp', 'integrations', 'third_party', 'scripts',
          'release.json', 'requirements.txt', 'macos-installer/GlyphsMCPInstaller/Info.plist',
          'macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj')


def input_digest(root, runtime, toolchain=''):
    digest = hashlib.sha256(str(Path(root).resolve()).encode())
    digest.update(toolchain.encode())
    for label, base in [(name, Path(root) / name) for name in INPUTS] + [('private-runtime', Path(runtime).resolve())]:
        paths = sorted(base.rglob('*')) if base.is_dir() else [base]
        digest.update((label + '\0' + str(base)).encode())
        for path in paths:
            if label != 'private-runtime' and ('__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo'} or path.name == '.DS_Store'): continue
            relative = path.relative_to(base) if base.is_dir() else Path(path.name)
            digest.update(str(relative).encode() + b'\0')
            if path.is_symlink():
                digest.update(('link:' + os.readlink(path)).encode())
                if path.is_dir():
                    # Internal directory targets are also enumerated normally.
                    # External directory trees are not safe cache inputs.
                    path.resolve().relative_to(base.resolve())
            if path.is_file():
                content = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''): content.update(chunk)
                digest.update(content.digest())
            elif not path.exists(): digest.update(b'missing')
            digest.update(b'\0')
    return digest.hexdigest()


def toolchain_identity():
    return json.dumps([sys.version, platform.machine(), os.environ.get('DEVELOPER_DIR'),
        subprocess.check_output(['xcrun', 'clang', '--version'], text=True),
        subprocess.check_output(['xcrun', '--show-sdk-path'], text=True)])


def stage(output, *, root=ROOT, runtime=None, builder=build_payload, validator=validate_payload, toolchain=None):
    output = Path(output)
    runtime = Path(runtime or os.environ.get('GMCP_BUILD_RUNTIME_ROOT') or root / 'build/private-runtime')
    toolchain = toolchain_identity() if toolchain is None else toolchain
    before = input_digest(root, runtime, toolchain)
    stamp = output.parent / ('.' + output.name + '-development-inputs.json')
    try:
        if json.loads(stamp.read_text()).get('inputs') == before:
            manifest = validator(output)  # Verify bytes; a receipt alone is insufficient.
            return dict(reused=True, inputs=before, manifest=manifest)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    stamp.unlink(missing_ok=True)
    manifest = builder(output, allow_outside_worktree=True, runtime_root=runtime)
    if input_digest(root, runtime, toolchain) != before:
        raise RuntimeError('Payload inputs changed during development build; cache not accepted.')
    stamp.write_text(json.dumps(dict(inputs=before)) + '\n')
    return dict(reused=False, inputs=before, manifest=manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if (os.environ.get('CONFIGURATION') != 'Debug' or os.environ.get('CODE_SIGNING_ALLOWED') != 'NO'
            or os.environ.get('GMCP_DEVELOPMENT_PAYLOAD_CACHE') != '1'):
        parser.error('Payload reuse requires explicit unsigned Debug development mode.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with (args.output.parent / '.development-payload.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        print(json.dumps(stage(args.output), sort_keys=True))


if __name__ == '__main__': main()
