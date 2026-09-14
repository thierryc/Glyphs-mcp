"""One-time relocation of explicitly evidenced installer backups, never a scan/installer."""
import argparse,hashlib,json,re,shutil,uuid
from pathlib import Path

PATTERN=re.compile(r'(glyphs|glyphs-mcp-[a-z-]+)\.bak-\d{8}-\d{6}(?:-[A-Fa-f0-9-]+)?$')

def hashes(root):
    if root.is_symlink() or not root.is_dir():raise ValueError('Expected an ordinary backup directory')
    result={}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('Symlink in backup: '+str(p))
        if p.is_file():result[p.relative_to(root).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return result

def archive(discovery, evidence, *, apply=False):
    discovery=Path(discovery).resolve();items=[]
    for source,expected in evidence.items():
        p=Path(source)
        if p.parent!=discovery or not PATTERN.fullmatch(p.name):raise ValueError('Not an explicit installer backup path: '+source)
        relative={str(Path(k).relative_to(p)):v for k,v in expected.items()}
        if hashes(p)!=relative:raise ValueError('Backup differs from recorded evidence: '+source)
        items.append(dict(source=str(p),hashes=relative))
    # Validate every source before any move; leave unlisted directories untouched.
    root=discovery.parent/'glyphs-mcp-skill-backups'/('migration-'+str(uuid.uuid4()))
    for item in items:item['backup']=str(root/Path(item['source']).name)
    record=dict(state='planned',items=items)
    if apply:
        root.mkdir(parents=True)
        receipt=root/'migration.json';receipt.write_text(json.dumps(record,indent=2)+'\n')
        for item in items:
            source,dest=Path(item['source']),Path(item['backup'])
            shutil.copytree(source,dest)
            if hashes(dest)!=item['hashes'] or hashes(source)!=item['hashes']:raise ValueError('Backup changed during copy')
            shutil.rmtree(source)
            item['moved']=True;receipt.write_text(json.dumps(record,indent=2)+'\n')
        record['state']='archived';receipt.write_text(json.dumps(record,indent=2)+'\n')
        record['receipt']=str(receipt)
    return record

def restore(receipt):
    record=json.loads(Path(receipt).read_text())
    for item in record['items']:
        if Path(item['source']).exists():raise ValueError('Restore would overwrite '+item['source'])
        if hashes(Path(item['backup']))!=item['hashes']:raise ValueError('Archive changed')
    for item in record['items']:
        shutil.copytree(item['backup'],item['source'])
        if hashes(Path(item['source']))!=item['hashes']:raise ValueError('Restore verification failed')
    return dict(restored=True,backupsRetained=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--discovery',type=Path);p.add_argument('--evidence',type=Path);p.add_argument('--apply',action='store_true');p.add_argument('--restore',type=Path)
    a=p.parse_args()
    print(json.dumps(restore(a.restore) if a.restore else archive(a.discovery,json.loads(a.evidence.read_text()),apply=a.apply),indent=2))
