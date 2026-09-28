"""Font-scoped Git transactions. Never saves fonts, resets repositories or pushes."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

from glyphs_mcp_protocol.source_identity import source_hash, SourceError

MAX_FILES = 100_000
MAX_BYTES = 512 * 1024 * 1024
MAX_RECORD_BYTES = 8 * 1024 * 1024


class CheckpointError(RuntimeError):
    def __init__(self, code, message, *, details=None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details or {}


def fail(message, code='checkpoint_conflict'):
    raise CheckpointError(code, message)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode()


class Repository:
    def __init__(self, font, operation_directory, persist):
        self.font = Path(font).absolute()
        self.directory = Path(operation_directory)
        self.persist = persist
        self.root = self.font.parent
        self.root = Path(self.git('rev-parse', '--show-toplevel').decode().strip()).resolve()
        self.relative = self.font.relative_to(self.root).as_posix()
        self.key = hashlib.sha256(self.relative.encode()).hexdigest()[:24]
        self.actions = '.glyphs-mcp/actions/' + self.key
        self.gitdir = Path(self.git('rev-parse', '--absolute-git-dir').decode().strip())

    def git(self, *args, data=None, index=None, check=True, limit=32*1024*1024, consume=None):
        env = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
        env.update(GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0', LC_ALL='C', GIT_LITERAL_PATHSPECS='1')
        if index: env['GIT_INDEX_FILE'] = str(index)
        try:
            with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
                result = subprocess.run(['/usr/bin/git', '-c', 'core.fsmonitor=false', '-C', str(self.root), *args],
                    input=data, stdout=output, stderr=errors, env=env, timeout=30)
                if output.tell() > limit:
                    fail('Git output exceeds the requested read limit.', 'checkpoint_too_large')
                output.seek(0)
                stdout = consume(output) if consume is not None and result.returncode == 0 else output.read(limit)
                errors.seek(0); stderr = errors.read(2000)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CheckpointError('checkpoint_git_failed', 'Git did not complete: '+str(exc)[:500]) from exc
        if check and result.returncode:
            raise CheckpointError('checkpoint_git_failed', stderr.decode(errors='replace').strip())
        return stdout if result.returncode == 0 else b''

    def _path(self, value):
        path = Path(value)
        return path if path.is_absolute() else self.root/path

    def _head(self):
        return self.git('rev-parse', '--verify', 'HEAD', check=False).decode().strip() or None

    def _ref(self):
        ref = self.git('symbolic-ref', '-q', 'HEAD', check=False).decode().strip()
        if not ref.startswith('refs/heads/'):
            fail('Checkpoint creation requires an attached local branch.')
        return ref

    def _safe_state(self):
        if self.font.is_symlink() or self.font.resolve() != self.font:
            fail('The font path contains a symbolic link.')
        for name in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply', 'BISECT_LOG'):
            if self._path(self.git('rev-parse', '--git-path', name).decode().strip()).exists():
                fail('Finish the outstanding Git operation before checkpointing.')
        if self.git('ls-files', '--unmerged', '-z'):
            fail('Resolve Git conflicts before checkpointing.')
        if self.git('diff', '--cached', '--no-ext-diff', '--no-textconv', '--name-only', '-z', '--', self.relative, self.actions):
            fail('The intended font or its action records contain staged changes; resolve them before checkpointing.')
        for setting in ('core.sparseCheckout', 'core.autocrlf', 'commit.gpgsign'):
            value = self.git('config', '--get', setting, check=False).strip().lower()
            if value not in (b'', b'false', b'0', b'no', b'off'):
                fail('Checkpointing does not support this repository setting: '+setting, 'checkpoint_unsupported')
        hooks = self.git('config', '--path', '--get', 'core.hooksPath', check=False).decode().strip()
        folder = self._path(hooks) if hooks else self._path(self.git('rev-parse', '--git-path', 'hooks').decode().strip())
        for name in ('pre-commit', 'prepare-commit-msg', 'commit-msg', 'post-commit', 'post-rewrite', 'reference-transaction'):
            if os.access(folder/name, os.X_OK):
                fail('A Git hook requires a manual commit; checkpointing will not bypass it: '+name, 'checkpoint_hooks_required')
        self.git('var', 'GIT_AUTHOR_IDENT'); self.git('var', 'GIT_COMMITTER_IDENT')

    @contextmanager
    def _locks(self):
        held = []
        try:
            for name in ('index',):
                path = self._path(self.git('rev-parse', '--git-path', name).decode().strip()+'.lock')
                try:
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    fail('Another Git operation holds '+path.name+'. Reconcile it before retrying.')
                identity = os.fstat(fd).st_ino
                os.close(fd); held.append((path, identity))
            yield held[0][0]
        finally:
            for path, identity in held:
                if path.exists() and path.stat().st_ino == identity:
                    path.unlink()

    def _snapshot(self, expected):
        try:
            if source_hash(self.font) != expected:
                fail('The saved font changed after verification.', 'checkpoint_source_changed')
            files = [self.font] if self.font.is_file() else sorted(p for p in self.font.rglob('*') if p.is_file())
            if len(files) > MAX_FILES or sum(p.stat().st_size for p in files) > MAX_BYTES:
                fail('The font exceeds checkpoint limits (100,000 files or 512 MiB).', 'checkpoint_too_large')
            values = {}
            for path in files:
                name = path.relative_to(self.root).as_posix()
                if any(ord(c) < 32 for c in name) or '\\' in name:
                    fail('The font contains an unsupported path.')
            # One Git process, literal absolute paths, and no filters. Git's
            # stdin-paths accepts quoted C strings; JSON quoting is compatible
            # here because control characters have already been rejected.
            data = ''.join(json.dumps(str(path), ensure_ascii=False)+'\n' for path in files).encode()
            hashes = self.git('hash-object', '-w', '--no-filters', '--stdin-paths', data=data).decode().splitlines()
            if len(hashes) != len(files):
                fail('Git returned incomplete font blob identities.')
            for path, oid in zip(files, hashes):
                mode = '100755' if path.stat().st_mode & stat.S_IXUSR else '100644'
                values[path.relative_to(self.root).as_posix()] = (mode, oid)
            if source_hash(self.font) != expected:
                fail('The saved font changed while checkpointing.', 'checkpoint_source_changed')
            return values
        except SourceError as exc:
            raise CheckpointError('checkpoint_source_changed', str(exc)) from exc

    def _attributes(self, paths):
        raw = self.git('check-attr', '-z', '--stdin', 'filter', 'text', 'eol', 'working-tree-encoding', 'ident',
                       data=b''.join(p.encode()+b'\0' for p in paths))
        parts = raw.split(b'\0')[:-1]
        if any(parts[i] not in (b'unspecified', b'unset') for i in range(2, len(parts), 3)):
            fail('Git attributes may transform font or action-record bytes. Resolve them before checkpointing.', 'checkpoint_unsupported')

    def tree_entries(self, revision, path=None):
        if not revision: return {}
        self.validate_revision(revision)
        raw = self.git('ls-tree', '-r', '-z', revision, '--', path or self.relative)
        if len(raw) > 32*1024*1024: fail('The checkpoint tree is too large.', 'checkpoint_too_large')
        result = {}
        for row in raw.split(b'\0'):
            if not row: continue
            metadata, name = row.split(b'\t', 1)
            mode, kind, oid = metadata.decode().split()
            if kind != 'blob' or mode not in {'100644', '100755'}:
                fail('The checkpoint contains links or nested repositories.', 'checkpoint_unsupported')
            result[name.decode()] = (mode, oid)
        return result

    @staticmethod
    def validate_revision(revision):
        if not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', revision):
            fail('Use the exact checkpoint revision returned by history.', 'invalid_request')

    def _update_index(self, index, entries, remove):
        zeros = '0' * (64 if self.git('rev-parse', '--show-object-format').strip() == b'sha256' else 40)
        data = b''.join(('0 '+zeros+'\t'+p).encode()+b'\0' for p in remove)
        data += b''.join((mode+' '+oid+'\t'+p).encode()+b'\0' for p,(mode,oid) in entries.items())
        self.git('update-index', '-z', '--index-info', data=data, index=index)

    def _publish(self, ref, new, old):
        self.git('update-ref', ref, new, old or '0'*len(new))

    def checkpoint(self, expected, operation_id, record, *, transaction=None, scopes=None):
        if not re.fullmatch('[A-Za-z0-9_-]{1,128}', operation_id): fail('Invalid checkpoint operation identity.')
        self.directory.mkdir(parents=True, exist_ok=True)
        with self._locks() as index_lock:
            if transaction and transaction.get('revision'):
                return self._reconcile(transaction, expected, index_lock)
            self._safe_state()
            ref, head = self._ref(), self._head()
            files = self._snapshot(expected)
            self._attributes(files)
            if files == self.tree_entries(head) and not record.get('actions'):
                return dict(status='reused', revision=head, sourceHash=expected, fontPath=self.relative)
            record_path = self.actions+'/'+operation_id+'.json'
            value = {**record, 'fontPath':self.relative, 'sourceHash':expected}
            data = json_bytes(value)
            if len(data) > MAX_RECORD_BYTES: fail('The action record exceeds 8 MiB.', 'checkpoint_too_large')
            records = {record_path:data}
            for name, content in (scopes or {}).items():
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}\.json', name): fail('Invalid scope record name.')
                records[self.actions+'/'+name] = json_bytes(content)
            if sum(len(data) for data in records.values()) > 64*1024*1024:
                fail('Action evidence exceeds 64 MiB.', 'checkpoint_too_large')
            self._attributes(records)
            for name, contents in records.items():
                path = self.root/name
                if path.resolve() != path: fail('The action-record path contains a symbolic link.')
                if path.exists() and path.read_bytes() != contents: fail('An action record already exists with different evidence.')
            entries = {**files, **{name:('100644', self.git('hash-object', '-w', '--no-filters', '--stdin', data=data).decode().strip()) for name,data in records.items()}}
            commit_index = self.directory/'commit-index'; commit_index.unlink(missing_ok=True)
            self.git('read-tree', head or '--empty', index=commit_index)
            old_names = list(self.tree_entries(head))
            self._update_index(commit_index, entries, old_names)
            tree = self.git('write-tree', index=commit_index).decode().strip()
            message = 'Font checkpoint: '+str(record.get('intendedChange') or self.font.name).replace('\n',' ')[:180]
            revision = self.git('commit-tree', tree, *(['-p',head] if head else []), '-m', message).decode().strip()
            real_index = self._path(self.git('rev-parse', '--git-path', 'index').decode().strip())
            next_index = self.directory/'next-index'; next_index.unlink(missing_ok=True)
            index_before = hashlib.sha256(real_index.read_bytes()).hexdigest() if real_index.exists() else None
            if real_index.exists(): shutil.copyfile(real_index, next_index)
            else: self.git('read-tree', '--empty', index=next_index)
            self._update_index(next_index, entries, old_names)
            txn = dict(status='prepared', revision=revision, previousRevision=head, ref=ref,
                       recordPath=record_path, fontPath=self.relative, sourceHash=expected,
                       indexBefore=index_before, indexAfter=hashlib.sha256(next_index.read_bytes()).hexdigest(),
                       recordFiles=list(records))
            self.persist(txn)  # Existing save/job record before the reference can move.
            if self._head() != head or self._ref() != ref or source_hash(self.font) != expected:
                fail('The branch or saved font changed before checkpoint publication.')
            self._publish(ref, revision, head)
            return self._reconcile(txn, expected, index_lock)

    def _reconcile(self, txn, expected, index_lock):
        if self._head() == txn['previousRevision']:
            self._safe_state()
            if (self._ref() != txn['ref'] or txn['sourceHash'] != expected
                    or self.tree_entries(txn['revision']) != self._snapshot(expected)):
                fail('The unpublished checkpoint no longer matches its baseline.')
            real_index = self._path(self.git('rev-parse', '--git-path', 'index').decode().strip())
            digest = hashlib.sha256(real_index.read_bytes()).hexdigest() if real_index.exists() else None
            if digest != txn['indexBefore']:
                fail('The index changed before retry; no staged content was replaced.')
            self._publish(txn['ref'], txn['revision'], txn['previousRevision'])
        # update-ref also locks HEAD for its reflog. Acquire our HEAD lock only
        # after publication, then verify the symbolic binding before index work.
        lock = self._path(self.git('rev-parse', '--git-path', 'HEAD').decode().strip()+'.lock')
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            fail('Another Git operation holds HEAD.lock; reconcile before retrying.')
        os.close(fd)
        try:
            return self._reconcile_locked(txn, expected, index_lock)
        finally:
            lock.unlink(missing_ok=True)

    def _reconcile_locked(self, txn, expected, index_lock):
        revision = txn['revision']; self.validate_revision(revision)
        if txn['sourceHash'] != expected or self.relative != txn['fontPath']:
            fail('The checkpoint retry no longer matches its saved font.')
        if self._ref() != txn['ref']: fail('The branch changed; reconcile the checkpoint manually.')
        head = self._head()
        if head == txn['previousRevision']:
            fail('Checkpoint publication did not finish. Refresh the saved result before creating another checkpoint.', 'checkpoint_not_published')
        if head != revision:
            fail('The branch changed after checkpoint publication; reconcile its index manually.')
        real_index = self._path(self.git('rev-parse', '--git-path', 'index').decode().strip())
        digest = hashlib.sha256(real_index.read_bytes()).hexdigest() if real_index.exists() else None
        if digest not in {txn['indexBefore'], txn['indexAfter']}:
            fail('The Git index changed after checkpoint publication; no staged content was replaced.')
        for name in txn['recordFiles']:
            path = self.root/name; data = self.git('show', revision+':'+name)
            if path.resolve() != path: fail('An action-record path changed.')
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                if path.read_bytes() != data: fail('An action record changed after checkpoint publication.')
            else:
                with path.open('xb') as stream: stream.write(data)
        if digest != txn['indexAfter']:
            candidate = self.directory/'next-index'
            if hashlib.sha256(candidate.read_bytes()).hexdigest() != txn['indexAfter']:
                fail('The checkpoint index evidence is unavailable.')
            shutil.copyfile(candidate, index_lock)
            os.replace(index_lock, real_index)
        # Blob identities were produced with --no-filters; compare again against disk.
        if self.tree_entries(revision) != self._snapshot(expected):
            fail('The committed font no longer matches the verified save.', 'checkpoint_source_changed')
        result = {**txn, 'status':'created'}
        self.persist(result)
        return result
