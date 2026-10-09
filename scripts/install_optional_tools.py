#!/usr/bin/env python3
"""Optional verified distributions. Never installs Python packages or starts Glyphs."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
from installation_transaction import InstallationTransaction, write_json
from build_simple_v2 import _identity

IDS = ('diffenator', 'beztrace-glyphs')
MAX_ARCHIVE = 512 * 1024 * 1024


def checksum(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''): digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value or '\0' in value:
        raise ValueError('Invalid distribution path')
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(x in ('.', '..') for x in value.split('/')):
        raise ValueError('Unsafe distribution path')
    return value


def regular_ancestors(path):
    for parent in (path, *path.parents):
        if parent.is_symlink() and str(parent) not in ('/tmp', '/var'):
            raise ValueError('Preserve symbolic link: ' + str(parent))


def extract(archive, output, inventory):
    if not isinstance(inventory, dict) or not inventory or len(inventory) > 20000:
        raise ValueError('Distribution inventory is unavailable')
    expected = {safe_relative(k): v for k, v in inventory.items()}
    observed, total = set(), 0
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            name = entry.filename.rstrip('/')
            safe_relative(name)
            mode = entry.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR) or entry.flag_bits & 1:
                raise ValueError('Distribution contains an unsupported file')
            if entry.is_dir(): continue
            if name in observed or name not in expected:
                raise ValueError('Distribution contains duplicate or unlisted files')
            total += entry.file_size
            if total > MAX_ARCHIVE * 2: raise ValueError('Expanded distribution is too large')
            target = output / name; target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as data, target.open('xb') as stream:
                size = 0
                while chunk := data.read(65536):
                    size += len(chunk)
                    if size > entry.file_size: raise ValueError('ZIP size differs')
                    stream.write(chunk)
            target.chmod(0o755 if mode & 0o111 else 0o644)
            if checksum(target) != expected[name]: raise ValueError('Distribution checksum differs: ' + name)
            observed.add(name)
    if observed != set(expected): raise ValueError('Distribution inventory is incomplete')


def verify_trust(root, release):
    team = release['teamID']
    if not isinstance(team, str) or len(team) != 10 or not team.isalnum(): raise ValueError('Invalid signing team')
    subjects = release.get('trustSubjects')
    if not isinstance(subjects, list) or not subjects: raise ValueError('No trust subjects supplied')
    for name in subjects:
        target = root if name == '.' else root / safe_relative(name)
        subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(target)], check=True, capture_output=True)
        detail = subprocess.run(['/usr/bin/codesign', '-dv', '--verbose=4', str(target)], check=True, capture_output=True, text=True)
        if ('TeamIdentifier=' + team) not in detail.stderr.splitlines(): raise ValueError('Distribution signing team differs')
        # Plug-ins and command-line tools are installed code, not application
        # bundles. Execute assessment rejects valid notarized non-app bundles.
        assessment = subprocess.run(['/usr/sbin/spctl', '--assess', '--type', 'install', '-vv', str(target)],
                                    check=True, capture_output=True, text=True)
        if 'source=Notarized Developer ID' not in assessment.stderr.splitlines():
            raise ValueError('Distribution lacks a verified notarization ticket')


def owned(receipt, target):
    if target.is_symlink(): raise ValueError('Development links are preserved')
    if not target.exists(): return
    if receipt is None or receipt.get('target') != str(target) or receipt.get('identity') != _identity(target):
        raise ValueError('Modified or unowned installation is preserved: ' + str(target))


class OptionalTools:
    def __init__(self, home, catalog):
        self.home = Path(home)
        self.root = self.home / 'Library/Application Support/Glyphs MCP/optional-tools'
        self.catalog = json.loads(Path(catalog).read_text())
        if self.catalog.get('schemaVersion') != 1 or set(self.catalog.get('tools', {})) != set(IDS):
            raise ValueError('Invalid optional tool catalog')

    def receipt_path(self, tool): return self.root / ('receipt-' + tool + '.json')
    def read_receipt(self, tool):
        path = self.receipt_path(tool)
        regular_ancestors(path)
        return json.loads(path.read_text()) if path.exists() else None

    def target(self, tool, release):
        if tool == 'beztrace-glyphs':
            return self.home / 'Library/Application Support/Glyphs 4/Plugins/Beztrace.glyphsPlugin'
        directory = release['directory']; safe_relative(directory)
        if '/' in directory: raise ValueError('Runtime directory must be one name')
        return self.root / 'diffenator' / directory

    def release(self, tool):
        item = self.catalog['tools'][tool]
        if item.get('status') != 'qualified': raise ValueError(item.get('reason', 'This distribution awaits release qualification'))
        import platform
        architecture = platform.machine()
        release = item.get('releases', {}).get(architecture)
        if release is None:
            raise ValueError('This optional distribution is not qualified for ' + architecture)
        minimum = release.get('minimumMacOS')
        if minimum is not None:
            if not isinstance(minimum, str) or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', minimum):
                raise ValueError('Invalid qualified macOS minimum')
            actual = platform.mac_ver()[0]
            version = lambda value: tuple(int(part) for part in (value.split('.') + ['0', '0'])[:3])
            if not actual or version(actual) < version(minimum):
                raise ValueError('This optional distribution requires macOS ' + minimum + ' or later')
        url = release['archiveURL']
        if not isinstance(url, str) or not url.startswith('https://github.com/'):
            raise ValueError('Optional distribution must use a pinned HTTPS release asset')
        if not isinstance(release['archiveSHA256'], str) or not re.fullmatch('[a-f0-9]{64}', release['archiveSHA256']):
            raise ValueError('Optional distribution checksum is missing')
        return release

    def status(self, tool):
        try:
            self.release(tool)
            available, reason = True, None
        except ValueError as exc:
            available, reason = False, str(exc)
        result = dict(id=tool, available=available, reason=reason, installed=False)
        receipt = self.read_receipt(tool)
        if receipt:
            target = Path(receipt['target'])
            if target != self.target(tool, receipt): raise ValueError('Invalid installation receipt target')
            result.update(installed=target.exists(), version=receipt.get('version'), build=str(receipt['build']) if receipt.get('build') is not None else None,
                          state='installed' if target.exists() else 'missing', loadedVerified=False)
            try:
                owned(receipt, target)
            except ValueError as exc:
                result.update(state='development_link' if target.is_symlink() else 'conflict', reason=str(exc))
            if tool == 'beztrace-glyphs' and result['state'] == 'installed':
                result['state'] = 'restart_required'
        elif tool == 'beztrace-glyphs':
            target = self.target(tool, {})
            if target.exists() or target.is_symlink():
                info = plistlib.loads((target / 'Contents/Info.plist').read_bytes()) if target.exists() else {}
                result.update(state='development_link' if target.is_symlink() else 'unmanaged',
                              version=info.get('CFBundleShortVersionString'), build=str(info['CFBundleVersion']) if info.get('CFBundleVersion') is not None else None, loadedVerified=False)
        return result

    def recovery_targets(self, tool, release=None):
        targets = {self.receipt_path(tool)}
        if tool == 'beztrace-glyphs':
            targets.update({self.target(tool, {}),
                            self.home / 'Library/Application Support/beztrace/engine-settings-v1.json',
                            self.home / 'Library/Application Support/beztrace/engines/0.1.1',
                            self.home / 'Library/Application Support/beztrace/engines/receipt-0.1.1.json'})
        else:
            targets.add(self.root / 'diffenator/current.json')
            receipt = self.read_receipt(tool)
            if receipt:
                targets.add(self.target(tool, receipt))
            if release:
                targets.add(self.target(tool, release))
            for item in self.catalog['tools'][tool].get('releases', {}).values():
                targets.add(self.target(tool, item))
        return targets

    @contextmanager
    def lock(self):
        regular_ancestors(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / '.optional-tools.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def install(self, tool, engine=None):
        release = self.release(tool)
        target = self.target(tool, release)
        receipt = self.read_receipt(tool)
        with self.lock():
            regular_ancestors(target)
            transaction_root = self.root / 'transactions' / tool; transaction_root.mkdir(parents=True, exist_ok=True)
            current = self.root / 'diffenator/current.json'
            config = self.home / 'Library/Application Support/beztrace/engine-settings-v1.json'
            engine_target = self.home / 'Library/Application Support/beztrace/engines/0.1.1'
            engine_receipt = engine_target.parent / 'receipt-0.1.1.json'
            InstallationTransaction.recover(transaction_root, self.recovery_targets(tool, release))
            receipt = self.read_receipt(tool)
            owned(receipt, target)
            with tempfile.TemporaryDirectory(prefix='optional-stage-', dir=self.root) as temporary:
                stage = Path(temporary); archive = stage / 'distribution.zip'
                expected_size = release['archiveSize']
                if type(expected_size) is not int or not 0 < expected_size <= MAX_ARCHIVE: raise ValueError('Invalid archive size')
                with urllib.request.urlopen(release['archiveURL'], timeout=30) as response, archive.open('xb') as output:
                    total = 0
                    while chunk := response.read(65536):
                        total += len(chunk)
                        if total > expected_size: raise ValueError('Download exceeds declared size')
                        output.write(chunk)
                if total != expected_size or checksum(archive) != release['archiveSHA256']: raise ValueError('Downloaded distribution differs')
                unpacked = stage / 'unpacked'; unpacked.mkdir()
                extract(archive, unpacked, release['files'])
                payload = unpacked / safe_relative(release['payloadRoot'])
                verify_trust(payload, release)
                next_receipt = dict(release, target=str(target), identity=_identity(payload), installedAt=time.time())
                changes = [(payload, target)]
                if tool == 'diffenator':
                    manifest = json.loads((payload / 'runtime.json').read_text())
                    if manifest.get('sourceRevision') != 'cecdab703d462cfea25b748b19ea4813d3f4d680' or manifest.get('tool') != 'diffenator2':
                        raise ValueError('Unqualified Diffenator runtime')
                    from platform import machine
                    architecture = 'arm64' if machine() == 'arm64' else 'x86_64'
                    if manifest.get('schemaVersion') != 1 or manifest.get('architecture') != architecture or manifest.get('pythonVersion') != '3.11.16':
                        raise ValueError('Incompatible Diffenator runtime metadata')
                    inventory = manifest.get('files')
                    if not isinstance(inventory, dict) or 'bin/python3' not in inventory:
                        raise ValueError('Diffenator runtime inventory is missing')
                    for relative, expected in inventory.items():
                        path = payload / safe_relative(relative)
                        if not path.is_file() or 'sha256:' + checksum(path) != expected:
                            raise ValueError('Diffenator runtime inventory differs')
                    actual = {path.relative_to(payload).as_posix() for path in payload.rglob('*') if path.is_file()}
                    if actual != set(inventory) | {'runtime.json'}:
                        raise ValueError('Diffenator runtime contains unlisted files')
                    pointer = stage / 'pointer.json'; write_json(pointer, dict(directory=release['directory']))
                    regular_ancestors(current)
                    changes.append((pointer, current))
                else:
                    info = plistlib.loads((payload / 'Contents/Info.plist').read_bytes())
                    if (info.get('CFBundleIdentifier') != 'dev.beztrace.glyphs' or str(info.get('CFBundleVersion')) != str(release['build'])
                            or info.get('CFBundleShortVersionString') != release.get('version')):
                        raise ValueError('Beztrace bundle identity/build differs')
                    if release.get('engineConfiguration') != 'engine-settings-v1': raise ValueError('Companion lacks persistent engine support')
                    if engine is None: raise ValueError('Bundled engine is required')
                    engine = Path(engine); regular_ancestors(config); regular_ancestors(engine_target)
                    regular_ancestors(engine_receipt)
                    previous_engine = json.loads(engine_receipt.read_text()) if engine_receipt.exists() else None
                    if engine_target.exists():
                        expected = (previous_engine or {}).get('identity') or (receipt or {}).get('engineIdentity')
                        if expected != _identity(engine_target): raise ValueError('Unowned/modified engine is preserved')
                    manifest = json.loads((engine / 'integration-manifest.json').read_text())
                    if manifest.get('version') != '0.1.1': raise ValueError('Incompatible bundled engine')
                    if any(checksum(engine / safe_relative(name)) != expected for name, expected in manifest['files'].items()): raise ValueError('Bundled engine inventory differs')
                    verify_trust(engine, dict(teamID=release['teamID'], trustSubjects=['bin/beztrace']))
                    settings = json.loads(config.read_text()) if config.exists() else {'schemaVersion': 1}
                    if settings.get('schemaVersion') != 1: raise ValueError('Unsupported engine settings')
                    settings['managedEngine'] = str(engine_target / 'bin/beztrace')
                    config_stage = stage / 'engine-config.json'; write_json(config_stage, settings)
                    engine_receipt_stage = stage / 'engine-receipt.json'
                    write_json(engine_receipt_stage, dict(target=str(engine_target), identity=_identity(engine), version='0.1.1'))
                    changes += [(engine, engine_target), (config_stage, config), (engine_receipt_stage, engine_receipt)]
                    next_receipt.update(engineIdentity=_identity(engine), managedEngine=settings['managedEngine'])
                next_path = stage / 'receipt.json'; write_json(next_path, next_receipt)
                changes.append((next_path, self.receipt_path(tool)))
                InstallationTransaction(transaction_root, changes).apply()
        return self.status(tool)

    def remove(self, tool):
        with self.lock():
            transaction_root = self.root / 'transactions' / tool; transaction_root.mkdir(parents=True, exist_ok=True)
            InstallationTransaction.recover(transaction_root, self.recovery_targets(tool))
            receipt = self.read_receipt(tool)
            if not receipt: raise ValueError('No ownership receipt; existing installation is preserved')
            target = self.target(tool, receipt); regular_ancestors(target); owned(receipt, target)
            changes = [(None, target), (None, self.receipt_path(tool))]
            with tempfile.TemporaryDirectory(dir=self.root) as temporary:
                stage = Path(temporary)
                if tool == 'diffenator':
                    current = self.root / 'diffenator/current.json'; regular_ancestors(current)
                    if current.exists() and json.loads(current.read_text()).get('directory') != receipt['directory']:
                        raise ValueError('Changed runtime pointer is preserved')
                    changes.append((None, current))
                else:
                    config = self.home / 'Library/Application Support/beztrace/engine-settings-v1.json'; regular_ancestors(config)
                    if config.exists():
                        settings = json.loads(config.read_text())
                        if settings.get('managedEngine') == receipt.get('managedEngine'):
                            settings.pop('managedEngine'); next_config = stage / 'settings.json'; write_json(next_config, settings)
                            changes.append((next_config, config))
                    # The engine is shared with the standalone companion; preserve it.
                InstallationTransaction(transaction_root, changes).apply()
        return self.status(tool)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--tool', choices=IDS)
    parser.add_argument('--action', choices=('status', 'install', 'update', 'remove'), default='status')
    parser.add_argument('--engine', type=Path)
    args = parser.parse_args()
    try:
        tools = OptionalTools(args.home, args.catalog)
        if args.action == 'status': result = [tools.status(tool) for tool in IDS]
        elif args.tool is None: raise ValueError('Choose one optional tool')
        elif args.action == 'remove': result = tools.remove(args.tool)
        else: result = tools.install(args.tool, args.engine)
        print(json.dumps(dict(ok=True, data=result)))
        return 0
    except Exception as exc:
        print(json.dumps(dict(ok=False, error=dict(code='optional_setup_failed', message=str(exc)))))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
