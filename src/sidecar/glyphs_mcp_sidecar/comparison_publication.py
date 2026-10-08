"""Publication receipts bound to snapshotted compiled inputs, never a live font."""
import ctypes
import errno
import hashlib
import os
from pathlib import Path
import shutil
import sys
import time
from uuid import uuid4
from glyphs_mcp_protocol import canonical_json
from glyphs_mcp_protocol.font_comparison import validate_manifest
from . import artifact_publication as publication


def rename_exclusive(source, destination):
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        rename = libc.renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = rename(os.fsencode(source), os.fsencode(destination), 4)  # RENAME_EXCL
    elif hasattr(libc, 'renameat2'):
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        result = rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1)  # RENAME_NOREPLACE
    else:
        raise OSError(errno.ENOTSUP, 'Create-only directory publication is unsupported')
    if result:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), str(destination))


def receipt(service, job, target, manifest):
    return dict(jobId=job['id'], destination=str(target), inputHash=job['sourceHash'],
                inputs=job['inputs'], manifestHash=publication._manifest_hash(manifest),
                files=manifest['files'], entryPoint=manifest['entryPoint'],
                verification='staged_report_and_compiled_input_hashes', publishedAt=time.time())


def reconcile(service, job):
    request = job.get('publishRequest') or {}
    try:
        value = service.jobs.read_json(job['id'], 'receipt.json')
        manifest = validate_manifest(dict(files=value['files'], totalBytes=sum(x['size'] for x in value['files']), entryPoint=value['entryPoint']))
        target = Path(value['destination'])
        valid = (value['jobId'] == job['id'] and value['inputHash'] == job['sourceHash'] and value['inputs'] == job['inputs']
                 and value['verification'] == 'staged_report_and_compiled_input_hashes'
                 and value['manifestHash'] == publication._manifest_hash(manifest))
    except (OSError, KeyError, ValueError, TypeError):
        try:
            manifest = validate_manifest(service.jobs.read_json(job['id'], 'manifest.json'))
            target = Path(request['destination'])
            value = receipt(service, job, target, manifest)
            valid = True
        except (OSError, KeyError, ValueError, TypeError):
            valid = False
    if valid and target.is_absolute() and publication._validate_published_tree(target, manifest):
        service.jobs.write_json(job['id'], 'receipt.json', value)
        result = service.jobs.update(job['id'], status='accepted', receipt=value, publishRequest=None, error=None,
                                     entryPoint=str(target / manifest['entryPoint']))
        service.jobs.release_bulk_artifacts(job['id'])
        return result
    return service.jobs.update(job['id'], status='accept_uncertain', error=dict(code='publication_outcome_unknown',
                               message='Report publication could not be verified. Reconcile the original destination; no replay was attempted.'))


def accept(service, error, job, *, destination, include_preview=True):
    if job['status'] == 'accepted':
        if destination is not None and destination != job['receipt']['destination']:
            raise error('destination_conflict', 'This report was already published to another destination')
        return service._public(job, include_preview=include_preview)
    if job['status'] != 'ready':
        raise error('job_not_acceptable', 'The comparison report is not ready')
    target = publication._destination(destination, error)
    manifest = validate_manifest(service.jobs.read_json(job['id'], 'manifest.json'))
    staging = publication._validate_staging(service, job, manifest, error)
    inputs = service.jobs.read_json(job['id'], 'inputs.json')
    fingerprint = 'sha256:' + hashlib.sha256(canonical_json(inputs).encode()).hexdigest()
    if fingerprint != job['sourceHash'] or inputs != job['inputs']:
        raise error('input_conflict', 'Comparison input evidence changed after preparation')
    for item in [*inputs['baseline'], *inputs['candidate'], *([inputs['wordlist']] if 'wordlist' in inputs else [])]:
        name = item['snapshot']
        if not isinstance(name, str) or Path(name).name != name:
            raise error('input_conflict', 'Invalid comparison snapshot path')
        snapshot = service.jobs.path(job['id']) / name
        if snapshot.is_symlink() or not snapshot.is_file() or publication._sha256(snapshot) != item['sha256']:
            raise error('input_conflict', 'A comparison snapshot changed after preparation')
    temporary = target.parent / ('.' + target.name + '.comparison-' + uuid4().hex)
    service.jobs.update(job['id'], status='accepting', publishRequest=dict(destination=str(target)), error=None)
    try:
        temporary.mkdir(mode=0o700)
        for item in manifest['files']:
            out = temporary / item['path']
            out.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            shutil.copyfile(staging / item['path'], out, follow_symlinks=False)
            out.chmod(0o600)
        if not publication._validate_published_tree(temporary, manifest):
            raise error('artifact_conflict', 'Report copy failed verification')
        publication._fsync_tree(temporary)
        rename_exclusive(temporary, target)
        descriptor = os.open(target.parent, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
        value = receipt(service, job, target, manifest)
        service.jobs.write_json(job['id'], 'receipt.json', value)
        accepted = service.jobs.update(job['id'], status='accepted', receipt=value, publishRequest=None, error=None,
                                       entryPoint=str(target / manifest['entryPoint']))
        service.jobs.release_bulk_artifacts(job['id'])
        return service._public(accepted, include_preview=include_preview)
    except Exception as exc:
        if temporary.exists(): shutil.rmtree(temporary)
        if isinstance(exc, FileExistsError):
            service.jobs.update(job['id'], status='ready', publishRequest=None, error=None)
            raise error('destination_exists', 'Report destination appeared during publication') from exc
        if target.exists():
            try:
                reconciled = reconcile(service, service.jobs.get(job['id']))
                if reconciled['status'] == 'accepted': return service._public(reconciled, include_preview=include_preview)
            except OSError:
                pass  # Retain accepting + original destination for restart reconciliation.
        else:
            service.jobs.update(job['id'], status='ready', publishRequest=None, error=dict(code='publication_failed', message=str(exc)))
        raise error('publication_failed', str(exc)) from exc
