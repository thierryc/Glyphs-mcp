"""Durable replacement of the installer's explicitly managed files."""
import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path


def exists(path):
    return path.exists() or path.is_symlink()


def remove(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif exists(path):
        path.unlink()


def write_json(path, value):
    temporary = path.with_suffix('.writing')
    with temporary.open('w') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def file_signature(content):
    return [len(content), hashlib.sha256(content).hexdigest()]


def matches_file(path, signature):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return signature is None
    except OSError:
        return False
    with os.fdopen(descriptor, 'rb') as stream:
        if signature is None or not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            return False
        return file_signature(stream.read(signature[0] + 1)) == signature


class InstallationTransaction:
    def __init__(self, root, changes, expected_files=None):
        self.root = Path(tempfile.mkdtemp(prefix='transaction-', dir=root))
        self.backup = self.root / 'backup'; self.backup.mkdir()
        self.stage = self.root / 'stage'; self.stage.mkdir()
        self.journal = self.root / 'journal.json'
        self.data = {'state': 'prepared', 'entries': []}
        try:
            for index, (source, target) in enumerate(changes):
                target = Path(target)
                staged = self.stage / str(index)
                if source is not None:
                    source = Path(source)
                    if source.is_dir(): shutil.copytree(source, staged, symlinks=True)
                    else: shutil.copy2(source, staged)
                self.data['entries'].append({'target': str(target), 'stage': str(staged),
                    'backup': str(self.backup / target.name), 'existed': exists(target),
                    'replacement': source is not None, 'started': False})
                if expected_files is not None and target in expected_files:
                    original = expected_files[target]
                    self.data['entries'][-1].update(
                        expected_file=file_signature(original) if original is not None else None,
                        staged_file=file_signature(staged.read_bytes()), existed=original is not None)
            if len({e['backup'] for e in self.data['entries']}) != len(changes):
                raise ValueError('Managed installation destinations must have unique names')
            write_json(self.journal, self.data)
        except BaseException:
            remove(self.root)
            raise

    def apply(self, verify=None, before_rollback=None):
        try:
            self.data['state'] = 'applying'
            for entry in self.data['entries']:
                target, backup = Path(entry['target']), Path(entry['backup'])
                target.parent.mkdir(parents=True, exist_ok=True)
                guarded = 'expected_file' in entry
                if guarded and not matches_file(target, entry['expected_file']):
                    raise ValueError('Settings changed during setup. Try again: ' + str(target))
                entry['started'] = True
                write_json(self.journal, self.data)  # Intent precedes either rename.
                if entry['existed']: target.rename(backup)
                staged = Path(entry['stage'])
                if guarded:
                    if entry['existed'] and not matches_file(backup, entry['expected_file']):
                        raise ValueError('Settings changed during setup. Try again: ' + str(target))
                    try:
                        # Keep the staged inode for recovery and never replace a newer file.
                        os.link(staged, target)
                    except FileExistsError as error:
                        raise ValueError('Settings changed during setup. Try again: ' + str(target)) from error
                elif entry['replacement']:
                    staged.rename(target)
            if verify: verify()
            self.data['state'] = 'committed'
            write_json(self.journal, self.data)
        except BaseException:
            self.data['state'] = 'recovery_pending'
            if before_rollback: before_rollback()
            self.rollback()
            raise
        finally:
            if self.data['state'] in ('committed', 'restored'): remove(self.stage)

    def rollback(self):
        failures = []
        for entry in reversed(self.data['entries']):
            if not entry['started']: continue
            target, backup = Path(entry['target']), Path(entry['backup'])
            try:
                if 'expected_file' in entry and exists(target):
                    staged = Path(entry['stage'])
                    if (target.is_symlink() or not exists(staged) or not target.samefile(staged)
                            or not matches_file(target, entry['staged_file'])):
                        continue  # A newer settings file takes precedence over the backup.
                if exists(backup):
                    remove(target); backup.rename(target)
                elif not entry['existed']:
                    remove(target)
            except OSError as error:
                failures.append(str(error))
        self.data['state'] = 'recovery_failed' if failures else 'restored'
        self.data['errors'] = failures
        write_json(self.journal, self.data)
        if failures:
            raise RuntimeError('Installation recovery incomplete; retained journal: ' + str(self.journal))

    @classmethod
    def recover(cls, root, allowed_targets):
        recovered = []
        for journal in Path(root).glob('transaction-*/journal.json'):
            data = json.loads(journal.read_text())
            if data['state'] in ('committed', 'restored'): continue
            for entry in data['entries']:
                if Path(entry['target']) not in allowed_targets:
                    raise ValueError('Recovery journal has an unmanaged destination')
                for key in ('stage', 'backup'):
                    Path(entry[key]).resolve().relative_to(journal.parent.resolve())
            transaction = object.__new__(cls)
            transaction.journal, transaction.data = journal, data
            transaction.rollback()
            recovered.append(data)
        return recovered
