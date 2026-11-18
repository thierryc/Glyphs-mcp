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
MAX_ENGINE_SETTINGS = 16 * 1024


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


def read_engine_settings(path):
    regular_ancestors(path)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {'schemaVersion': 1}, None
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Beztrace engine settings must be a regular file')
        content = stream.read(MAX_ENGINE_SETTINGS + 1)
    if len(content) > MAX_ENGINE_SETTINGS:
        raise ValueError('Beztrace engine settings exceed 16 KiB')
    settings = json.loads(content)
    if not isinstance(settings, dict) or type(settings.get('schemaVersion')) is not int or settings['schemaVersion'] != 1:
        raise ValueError('Unsupported Beztrace engine settings')
    for key in ('userEngine', 'managedEngine'):
        if key in settings:
            path = settings[key]
            if not isinstance(path, str) or not Path(path).is_absolute() or '\0' in path:
                raise ValueError('Invalid Beztrace engine path: ' + key)
    return settings, content


def engine_subset(target, source):
    """A missing file is repairable if all surviving entries match the verified engine."""
    if not target.is_dir() or target.is_symlink():
        return False
    for path in target.rglob('*'):
        counterpart = source / path.relative_to(target)
        mode = path.lstat().st_mode
        if counterpart.is_symlink() or not counterpart.exists() or mode != counterpart.stat().st_mode:
            return False
        if stat.S_ISREG(mode):
            if checksum(path) != checksum(counterpart):
                return False
        elif not stat.S_ISDIR(mode):
            return False
    return True


class OptionalTools:
    def __init__(self, home, catalog):
        self.home = Path(home)
        self.root = self.home / 'Library/Application Support/Glyphs MCP/optional-tools'
        self.catalog = json.loads(Path(catalog).read_text())
        if self.catalog.get('schemaVersion') != 1 or set(self.catalog.get('tools', {})) != set(IDS):
            raise ValueError('Invalid optional tool catalog')

    def receipt_path(self, tool): return self.root / ('receipt-' + tool + '.json')

    def engine_settings_path(self):
        return self.home / 'Library/Application Support/beztrace/engine-settings-v1.json'

    def engine_paths(self):
        version = self.catalog['tools']['beztrace-glyphs']['engineVersion']
        if not isinstance(version, str) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
            raise ValueError('Invalid bundled engine version')
        root = self.home / 'Library/Application Support/beztrace/engines'
        return version, root / version, root / ('receipt-' + version + '.json')

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

    def status(self, tool, engine=None):
        try:
            release = self.release(tool)
            available, reason = True, None
        except ValueError as exc:
            release = None
            available, reason = False, str(exc)
        result = dict(id=tool, available=available, reason=reason, installed=False,
                      distributionQualified=self.catalog['tools'][tool].get('status') == 'qualified')
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
                result['installedAt'] = receipt.get('installedAt')
                result['updateAvailable'] = release is not None and (
                    int(receipt['build']) < int(release['build']) or (
                        int(receipt['build']) == int(release['build']) and
                        receipt.get('engineExecutable') != str(self.engine_paths()[1] / 'bin/beztrace')
                    )
                )
                if receipt.get('engineConfiguration') == 'engine-settings-v1':
                    result.update(self.beztrace_engine_status(receipt))
                else:
                    result['engineStatus'] = 'manual'
        elif tool == 'beztrace-glyphs':
            target = self.target(tool, {})
            if target.exists() or target.is_symlink():
                info = plistlib.loads((target / 'Contents/Info.plist').read_bytes()) if target.exists() else {}
                result.update(state='development_link' if target.is_symlink() else 'unmanaged',
                              version=info.get('CFBundleShortVersionString'), build=str(info['CFBundleVersion']) if info.get('CFBundleVersion') is not None else None, loadedVerified=False)
        if tool == 'beztrace-glyphs' and available and result.get('state') in (None, 'installed', 'missing'):
            _, target, _ = self.engine_paths()
            try:
                self.check_engine_destination(target, receipt, Path(engine) if engine is not None else None)
            except (OSError, ValueError):
                result['engineConflictPath'] = str(target)
        return result

    def beztrace_engine_status(self, receipt):
        try:
            settings, _ = read_engine_settings(self.engine_settings_path())
        except (OSError, ValueError, RecursionError):
            return {'engineStatus': 'invalid_settings'}
        if 'userEngine' in settings:
            executable = Path(settings['userEngine'])
            return {'engineStatus': 'custom' if executable.is_file() and os.access(executable, os.X_OK)
                    else 'missing_custom'}
        managed = receipt.get('managedEngine')
        if managed is None or settings.get('managedEngine') != managed:
            return {'engineStatus': 'repair'}
        executable = Path(managed)
        if (executable.name != 'beztrace' or executable.parent.name != 'bin'
                or executable.parents[2] != self.engine_settings_path().parent / 'engines'
                or not executable.is_file() or not os.access(executable, os.X_OK)):
            return {'engineStatus': 'repair'}
        try:
            regular_ancestors(executable)
            if _identity(executable.parent.parent) == receipt.get('engineIdentity'):
                return {'engineStatus': 'managed'}
        except (OSError, ValueError):
            pass
        return {'engineStatus': 'repair'}

    def check_engine_destination(self, target, receipt, source, source_identity=None):
        regular_ancestors(target)
        if not target.exists():
            return
        _, _, engine_receipt = self.engine_paths()
        regular_ancestors(engine_receipt)
        previous = json.loads(engine_receipt.read_text()) if engine_receipt.exists() else {}
        expected = previous.get('identity') if previous.get('target') == str(target) else None
        if expected is None and (receipt or {}).get('engineExecutable') == str(target / 'bin/beztrace'):
            expected = receipt.get('engineIdentity')
        if expected and source is not None and source.is_dir():
            # Require the previous release identity before treating a subset as owned.
            source_identity = source_identity or _identity(source)
            if engine_subset(target, source) and (expected == source_identity or expected == _identity(target)):
                return
        elif expected and target.is_dir() and _identity(target) == expected:
            return
        raise ValueError('An existing Beztrace engine needs review. Move this folder to a backup location, then try again: ' + str(target))

    def recovery_targets(self, tool, release=None):
        targets = {self.receipt_path(tool)}
        if tool == 'beztrace-glyphs':
            _, engine_target, engine_receipt = self.engine_paths()
            targets.update({self.target(tool, {}),
                            self.home / 'Library/Application Support/beztrace/engine-settings-v1.json',
                            engine_target, engine_receipt,
                            # Recover interrupted transactions from the previous catalog, too.
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
        with self.lock():
            regular_ancestors(target)
            transaction_root = self.root / 'transactions' / tool; transaction_root.mkdir(parents=True, exist_ok=True)
            current = self.root / 'diffenator/current.json'
            config = self.engine_settings_path()
            if tool == 'beztrace-glyphs':
                engine_version, engine_target, engine_receipt = self.engine_paths()
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
                next_receipt = dict(release, target=str(target), identity=_identity(payload))
                changes = [(payload, target)]
                expected_files = {}
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
                    configuration = release.get('engineConfiguration')
                    if configuration not in ('engine-settings-v1', 'manual-selection'):
                        raise ValueError('Unsupported companion engine configuration')
                    if engine is None: raise ValueError('Bundled engine is required')
                    engine = Path(engine)
                    regular_ancestors(engine_receipt)
                    manifest = json.loads((engine / 'integration-manifest.json').read_text())
                    if manifest.get('version') != engine_version: raise ValueError('Incompatible bundled engine')
                    if any(checksum(engine / safe_relative(name)) != expected for name, expected in manifest['files'].items()): raise ValueError('Bundled engine inventory differs')
                    verify_trust(engine, dict(teamID=release['teamID'], trustSubjects=['bin/beztrace']))
                    engine_identity = _identity(engine)
                    self.check_engine_destination(engine_target, receipt, engine, engine_identity)
                    if configuration == 'engine-settings-v1':
                        settings, original = read_engine_settings(config)
                        settings['managedEngine'] = str(engine_target / 'bin/beztrace')
                        config_stage = stage / 'engine-config.json'; write_json(config_stage, settings)
                        if config_stage.stat().st_size > MAX_ENGINE_SETTINGS:
                            raise ValueError('Beztrace engine settings exceed 16 KiB')
                        expected_files[config] = original
                        next_receipt['managedEngine'] = settings['managedEngine']
                    engine_receipt_stage = stage / 'engine-receipt.json'
                    write_json(engine_receipt_stage, dict(target=str(engine_target), identity=engine_identity, version=engine_version))
                    changes += [(engine, engine_target), (engine_receipt_stage, engine_receipt)]
                    next_receipt.update(engineIdentity=engine_identity, engineExecutable=str(engine_target / 'bin/beztrace'))
                next_receipt['installedAt'] = time.time()
                next_path = stage / 'receipt.json'; write_json(next_path, next_receipt)
                changes.append((next_path, self.receipt_path(tool)))
                if expected_files:
                    changes.append((config_stage, config))
                InstallationTransaction(transaction_root, changes, expected_files=expected_files).apply()
        return self.status(tool, engine)

    def remove(self, tool, engine=None):
        with self.lock():
            transaction_root = self.root / 'transactions' / tool; transaction_root.mkdir(parents=True, exist_ok=True)
            InstallationTransaction.recover(transaction_root, self.recovery_targets(tool))
            receipt = self.read_receipt(tool)
            if not receipt: raise ValueError('No ownership receipt; existing installation is preserved')
            target = self.target(tool, receipt); regular_ancestors(target); owned(receipt, target)
            changes = [(None, target), (None, self.receipt_path(tool))]
            expected_files = {}
            with tempfile.TemporaryDirectory(dir=self.root) as temporary:
                stage = Path(temporary)
                if tool == 'diffenator':
                    current = self.root / 'diffenator/current.json'; regular_ancestors(current)
                    if current.exists() and json.loads(current.read_text()).get('directory') != receipt['directory']:
                        raise ValueError('Changed runtime pointer is preserved')
                    changes.append((None, current))
                elif receipt.get('managedEngine'):
                    config = self.engine_settings_path()
                    try:
                        settings, original = read_engine_settings(config)
                    except (OSError, ValueError, RecursionError):
                        settings = {}
                    if settings.get('managedEngine') == receipt['managedEngine']:
                        settings.pop('managedEngine'); next_config = stage / 'settings.json'; write_json(next_config, settings)
                        changes.append((next_config, config))
                        expected_files[config] = original
                    # The engine is shared with the standalone companion; preserve it.
                InstallationTransaction(transaction_root, changes, expected_files=expected_files).apply()
        return self.status(tool, engine)


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
        if args.action == 'status': result = [tools.status(tool, args.engine) for tool in IDS]
        elif args.tool is None: raise ValueError('Choose one optional tool')
        elif args.action == 'remove': result = tools.remove(args.tool, args.engine)
        else: result = tools.install(args.tool, args.engine)
        print(json.dumps(dict(ok=True, data=result)))
        return 0
    except Exception as exc:
        print(json.dumps(dict(ok=False, error=dict(code='optional_setup_failed', message=str(exc)))))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
