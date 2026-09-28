"""On-demand, bounded font history. Does not inspect or modify a live editor."""
import base64
import json
from pathlib import Path
from .checkpoint_git import Repository, fail, MAX_BYTES, MAX_FILES, MAX_RECORD_BYTES


def _limit(value):
    if type(value) is not int or not 1 <= value <= 100:
        fail('Use a page limit from 1 to 100.', 'invalid_request')
    return value


def revision(repository, value):
    repository.validate_revision(value)
    ancestors = repository.git('merge-base', value, repository._head() or '')
    if ancestors.decode().strip() != value:
        fail('The requested revision is not in the current branch history.', 'checkpoint_revision_unavailable')
    return value


def history(repository, *, limit=20, cursor=None):
    _limit(limit);head=repository._head();offset=0
    if cursor:
        try:
            value=json.loads(base64.urlsafe_b64decode(cursor))
            if value['head'] != head or value['font'] != repository.relative:
                fail('History changed. Read the first page again.', 'stale_history')
            offset=value['offset']
            if type(offset) is not int or not 0 <= offset <= 100000:raise ValueError()
        except (ValueError, KeyError, TypeError):fail('Invalid history cursor.', 'invalid_request')
    if not head:return {'checkpoints':[], 'nextCursor':None}
    raw=repository.git('log','--format=%H%x00%ct%x00%s','--max-count='+str(limit+1),'--skip='+str(offset),head,'--',repository.relative,repository.actions,limit=256*1024)
    rows=[]
    for line in raw.decode(errors='replace').splitlines():
        parts=line.split('\0',2)
        if len(parts)!=3:fail('Git history could not be decoded.')
        rows.append(dict(revision=parts[0],timestamp=int(parts[1]),summary=parts[2][:500]))
    cursor=base64.urlsafe_b64encode(json.dumps({'head':head,'font':repository.relative,'offset':offset+limit}).encode()).decode() if len(rows)>limit else None
    return dict(checkpoints=rows[:limit],nextCursor=cursor,fontPath=repository.relative,head=head)


def details(repository, selected):
    revision(repository,selected)
    names=repository.git('diff-tree','--root','--no-commit-id','--name-only','-r','-z',selected,'--',repository.actions,limit=64*1024).split(b'\0')
    records=[];remaining=MAX_RECORD_BYTES
    for raw in names:
        if not raw or raw.endswith(b'_scope.json'):continue
        if len(records)>=100:fail('Too many action records in this revision.', 'checkpoint_too_large')
        data=repository.git('show',selected+':'+raw.decode(),limit=remaining)
        remaining-=len(data)
        try:value=json.loads(data)
        except ValueError:fail('The action record is not valid JSON.')
        if not isinstance(value,dict) or value.get('schemaVersion')!=1 or value.get('fontPath')!=repository.relative:
            fail('The action record does not match this font.')
        records.append(value)
    return dict(revision=selected,fontPath=repository.relative,records=records,
                evidence='Recorded actions may not explain all font changes; manual changes are possible.')


def scope(repository, selected, reference, *, offset=0, limit=100):
    revision(repository,selected);_limit(limit)
    if type(offset) is not int or offset<0:fail('Invalid scope offset.','invalid_request')
    if (not isinstance(reference,str) or not reference.startswith(repository.actions+'/')
            or not reference.endswith('_scope.json') or '/' in reference[len(repository.actions)+1:]):
        fail('Invalid action-scope reference.','invalid_request')
    value=json.loads(repository.git('show',selected+':'+reference,limit=64*1024*1024))
    if not isinstance(value,list):fail('Scope evidence is unavailable.')
    return dict(targets=value[offset:offset+limit],count=len(value),nextOffset=offset+limit if offset+limit<len(value) else None)


def compare(repository, before, after, *, offset=0, limit=100, file=None):
    revision(repository,before);revision(repository,after);_limit(limit)
    if type(offset) is not int or offset<0:fail('Invalid comparison offset.','invalid_request')
    left,right=repository.tree_entries(before),repository.tree_entries(after)
    changed=sorted(name for name in left.keys()|right.keys() if left.get(name)!=right.get(name))
    if file is not None:
        if file not in changed:fail('Choose a changed font file from this comparison.','invalid_request')
        def content(values):
            if file not in values:return None
            data=repository.git('cat-file','blob',values[file][1],limit=1024*1024)
            try:return data.decode('utf-8')
            except UnicodeError:fail('This file is binary; text comparison is unavailable.','checkpoint_binary')
        return dict(file=file,before=content(left),after=content(right))
    return dict(repository=str(repository.root),before=before,after=after,files=[dict(path=name,change='added' if name not in left else 'removed' if name not in right else 'modified') for name in changed[offset:offset+limit]],
                count=len(changed),nextOffset=offset+limit if offset+limit<len(changed) else None)


def materialize(repository, selected, destination):
    revision(repository,selected)
    entries=repository.tree_entries(selected)
    if not entries or len(entries)>MAX_FILES:fail('This revision has no supported font or exceeds the file limit.')
    root=Path(destination);root.mkdir(parents=True,exist_ok=False)
    output=root/repository.font.name
    def consume(stream):
        total=0
        for name,(mode,oid) in entries.items():
            relative=Path(name).relative_to(repository.relative)
            if relative.is_absolute() or '..' in relative.parts:fail('Unsafe historical font path.')
            header=stream.readline(128).decode('ascii').split()
            if len(header)!=3 or header[:2]!=[oid,'blob'] or not header[2].isdigit():
                fail('Git returned invalid historical font content.')
            size=int(header[2]);total+=size
            if total>MAX_BYTES:fail('The historical font exceeds the byte limit.','checkpoint_too_large')
            path=output/relative;path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as target:
                remaining=size
                while remaining:
                    data=stream.read(min(remaining,1024*1024))
                    if not data:fail('Git returned incomplete historical font content.')
                    target.write(data);remaining-=len(data)
            if stream.read(1)!=b'\n':fail('Invalid historical font boundary.')
            path.chmod(0o755 if mode=='100755' else 0o644)
        if stream.read(1):fail('Unexpected historical font content.')
    repository.git('cat-file','--batch',data=''.join(oid+'\n' for _,oid in entries.values()).encode(),
                   limit=MAX_BYTES+128*len(entries),consume=consume)
    return output


def read(service, document_id, entities, fields):
    if len(entities)!=1 or fields!=['checkpoint']:
        fail('Checkpoint reads require one selector and fields=[checkpoint].','invalid_request')
    document=service._document(document_id)
    if not document.get('path'):fail('Save the intended font before reading its history.','document_path_required')
    repository=Repository(document['path'],service.jobs.root,lambda _:None)
    value=dict(entities[0]);kind=value.pop('kind')
    calls={'checkpoint_history':history,'checkpoint_details':details,'checkpoint_compare':compare,'checkpoint_scope':scope}
    try:return [dict(kind=kind,checkpoint=calls[kind](repository,**value))]
    except TypeError as exc:fail('Invalid checkpoint read fields: '+str(exc)[:200],'invalid_request')
