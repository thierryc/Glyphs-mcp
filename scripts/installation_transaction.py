"""Durable replacement of the installer's explicitly managed files."""
import json
import os
import shutil
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


class InstallationTransaction:
    def __init__(self, root, changes):
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
                entry['started'] = True
                write_json(self.journal, self.data)  # Intent precedes either rename.
                if entry['existed']: target.rename(backup)
                if entry['replacement']: Path(entry['stage']).rename(target)
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
