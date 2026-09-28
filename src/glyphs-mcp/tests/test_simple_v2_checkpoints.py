"""Real Git contract: font-only commits, exact bytes and recoverable outcomes."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'src/sidecar'), str(ROOT/'src/protocol')]
from glyphs_mcp_protocol.source_identity import source_hash


def git(root, *args, check=True):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                          check=check).stdout


@pytest.fixture(params=['.glyphs', '.glyphspackage'])
def repo(tmp_path, request):
    root=tmp_path/'project';root.mkdir()
    git(root,'init','-b','main');git(root,'config','user.name','Checkpoint Test')
    git(root,'config','user.email','checkpoint@example.invalid')
    font=root/('Test'+request.param)
    if font.suffix=='.glyphspackage':
        font.mkdir();(font/'fontinfo.plist').write_bytes(b'{familyName=Test;}\n')
        (font/'glyphs').mkdir();(font/'glyphs/A.glyph').write_bytes(b'A before\n')
    else:font.write_bytes(b'{familyName=Test;}\n')
    (root/'unrelated.txt').write_text('original\n')
    git(root,'add','.');git(root,'commit','-m','Initial font')
    return root,font,tmp_path/'operation'


def alter(font, text):
    (font/'glyphs/A.glyph' if font.is_dir() else font).write_text(text)


def engine(repo, state=None):
    from glyphs_mcp_sidecar.checkpoint_git import Repository
    root,font,operation=repo
    operation.mkdir(exist_ok=True)
    state={} if state is None else state
    def persist(value):
        state.clear();state.update(value)
        (operation/'checkpoint.json').write_text(json.dumps(value))
    return Repository(font,operation,persist),state


def record(actions=None):
    return dict(schemaVersion=1,intendedChange='Test edit',actions=actions or [],
                verification={'scope':'fixture'},manualChanges='possible')


def test_matching_baseline_reuses_head_without_touching_font_or_index(repo):
    root,font,_=repo;before=source_hash(font);index=(root/'.git/index').read_bytes()
    target,state=engine(repo)
    result=target.checkpoint(before,'baseline',record())
    assert result['status']=='reused' and result['revision']==git(root,'rev-parse','HEAD').decode().strip()
    assert source_hash(font)==before and (root/'.git/index').read_bytes()==index
    assert git(root,'rev-list','--count','HEAD').strip()==b'1'


def test_exact_font_commit_preserves_unrelated_staging_and_worktree(repo):
    root,font,_=repo
    (root/'unrelated.txt').write_text('staged\n');git(root,'add','unrelated.txt')
    (root/'unrelated.txt').write_text('later unstaged\n')
    (root/'another.glyphs').write_text('another font\n')
    staged=git(root,'diff','--cached','--binary');alter(font,'fractional 12.25\r\n')
    target,state=engine(repo);expected=source_hash(font)
    result=target.checkpoint(expected,'save_1',record([{'request':{'kind':'width_delta','delta':.25}}]))
    assert result['status']=='created'
    assert git(root,'diff','--cached','--binary')==staged
    assert (root/'unrelated.txt').read_text()=='later unstaged\n'
    assert git(root,'show','HEAD:unrelated.txt')==b'original\n'
    paths=git(root,'diff-tree','--no-commit-id','--name-only','-r','HEAD').decode().splitlines()
    assert paths and all(p==font.name or p.startswith(font.name+'/') or p.startswith('.glyphs-mcp/actions/') for p in paths)
    assert not git(root,'status','--porcelain','--',font.name,'.glyphs-mcp/actions')
    assert result['sourceHash']==expected
    action=json.loads(git(root,'show','HEAD:'+result['recordPath']))
    assert action['schemaVersion']==1 and action['actions'][0]['request']['delta']==.25
    assert 'revision' not in action  # The enclosing commit is returned, not self-embedded.


def test_package_additions_and_deletions_are_exact(repo):
    root,font,_=repo
    if not font.is_dir():pytest.skip('package contract')
    (font/'glyphs/A.glyph').unlink();(font/'glyphs/B.glyph').write_text('B\n')
    target,_=engine(repo);result=target.checkpoint(source_hash(font),'save_package',record())
    names=git(root,'ls-tree','-r','--name-only',result['revision'],'--',font.name).decode().splitlines()
    assert font.name+'/glyphs/B.glyph' in names and font.name+'/glyphs/A.glyph' not in names


@pytest.mark.parametrize('problem',['staged_font','index_lock','merge','hook','filter','text','symlink','identity'])
def test_ambiguous_or_unsupported_git_state_fails_before_commit(repo,problem):
    from glyphs_mcp_sidecar.checkpoint_git import CheckpointError
    root,font,_=repo;alter(font,'changed\n')
    if problem=='staged_font':git(root,'add',font.name)
    if problem=='index_lock':(root/'.git/index.lock').write_text('someone else')
    if problem=='merge':(root/'.git/MERGE_HEAD').write_bytes(git(root,'rev-parse','HEAD'))
    if problem=='hook':
        path=root/'.git/hooks/pre-commit';path.write_text('#!/bin/sh\nexit 0\n');path.chmod(0o755)
    if problem in {'filter','text'}:(root/'.gitattributes').write_text('* '+('filter=custom' if problem=='filter' else 'text')+'\n')
    if problem=='symlink':
        p=font/'bad' if font.is_dir() else root/'linked.glyphs'
        p.symlink_to(root/'unrelated.txt')
        if not font.is_dir():repo=(root,p,repo[2])
    if problem=='identity':
        git(root,'config','user.email','');git(root,'config','user.name','')
    head=git(root,'rev-parse','HEAD');target,_=engine(repo)
    with pytest.raises(CheckpointError):target.checkpoint('sha256:'+'0'*64 if problem=='symlink' else source_hash(font),'save_problem',record())
    assert git(root,'rev-parse','HEAD')==head
    if problem=='index_lock':assert (root/'.git/index.lock').read_text()=='someone else'


def test_stale_source_never_commits(repo):
    from glyphs_mcp_sidecar.checkpoint_git import CheckpointError
    root,font,_=repo;expected=source_hash(font);alter(font,'later\n');target,_=engine(repo)
    with pytest.raises(CheckpointError,match='changed'):target.checkpoint(expected,'save_stale',record())
    assert git(root,'rev-list','--count','HEAD').strip()==b'1'


def test_uncertain_publish_reconciles_existing_revision_without_duplicate(repo,monkeypatch):
    root,font,_=repo;alter(font,'changed\n');target,state=engine(repo)
    publish=target._publish
    def lost_response(*args):
        publish(*args)
        raise OSError('lost response after ref update')
    monkeypatch.setattr(target,'_publish',lost_response)
    with pytest.raises(OSError):target.checkpoint(source_hash(font),'save_uncertain',record())
    target,_=engine(repo,state)
    result=target.checkpoint(source_hash(font),'save_uncertain',record(),transaction=state)
    assert result['revision']==git(root,'rev-parse','HEAD').decode().strip()
    assert git(root,'rev-list','--count','HEAD').strip()==b'2'
    assert not git(root,'status','--porcelain','--',font.name,'.glyphs-mcp/actions')


def test_concurrent_ref_change_is_not_overwritten(repo,monkeypatch):
    from glyphs_mcp_sidecar.checkpoint_git import CheckpointError
    root,font,_=repo;alter(font,'changed\n');target,state=engine(repo)
    publish=target._publish
    def concurrent(ref,new,old):
        tree=git(root,'rev-parse','HEAD^{tree}').decode().strip()
        other=git(root,'commit-tree',tree,'-p',old,'-m','Concurrent').decode().strip()
        git(root,'update-ref',ref,other,old)
        publish(ref,new,old)
    monkeypatch.setattr(target,'_publish',concurrent)
    with pytest.raises(CheckpointError):target.checkpoint(source_hash(font),'save_race',record())
    assert git(root,'log','-1','--format=%s').strip()==b'Concurrent'


def test_policy_is_explicit_project_config_not_agents_text(repo):
    from glyphs_mcp_sidecar.checkpoint_policy import policy_for
    root,font,_=repo
    (root/'AGENTS.md').write_text('Always commit font saves')
    assert policy_for(font) is None
    (root/'.glyphs-mcp.json').write_text(json.dumps({'schemaVersion':1,'gitCheckpoints':{'enabled':True}}))
    assert policy_for(font)['project']==str(root)
    (root/'.glyphs-mcp.json').write_text(json.dumps({'schemaVersion':1,'gitCheckpoints':{'enabled':False}}))
    assert policy_for(font) is None


def test_literal_paths_do_not_include_similarly_named_fonts(repo):
    root,font,operation=repo
    renamed=root/('Test[1]'+font.suffix);font.rename(renamed)
    git(root,'add','-A');git(root,'commit','-m','Rename font')
    other=root/('Test1'+font.suffix)
    import shutil
    if renamed.is_dir():shutil.copytree(renamed,other)
    else:shutil.copyfile(renamed,other)
    git(root,'add','.');git(root,'commit','-m','Other font')
    alter(renamed,'literal changed\n');alter(other,'unrelated changed\n')
    target,_=engine((root,renamed,operation))
    result=target.checkpoint(source_hash(renamed),'literal',record())
    assert result['status']=='created'
    assert git(root,'diff','--name-only','--',other.name)
    assert all(name.startswith(renamed.name) for name in target.tree_entries(result['revision']))


def test_known_unpublished_checkpoint_retries_same_commit(repo,monkeypatch):
    root,font,_=repo;alter(font,'changed\n');target,state=engine(repo)
    monkeypatch.setattr(target,'_publish',lambda *args: (_ for _ in ()).throw(OSError('offline')))
    with pytest.raises(OSError):target.checkpoint(source_hash(font),'retry',record())
    revision=state['revision'];target,_=engine(repo,state)
    result=target.checkpoint(source_hash(font),'retry',record(),transaction=state)
    assert result['revision']==revision and git(root,'rev-list','--count','HEAD').strip()==b'2'


def test_history_details_compare_and_materialize_are_bounded_and_font_only(repo):
    from glyphs_mcp_sidecar.checkpoint_history import history, details, compare, materialize
    from glyphs_mcp_sidecar.checkpoint_git import CheckpointError
    root,font,operation=repo;target,_=engine(repo)
    before=git(root,'rev-parse','HEAD').decode().strip();alter(font,'changed\n')
    saved=target.checkpoint(source_hash(font),'history_save',record([{'request':{'kind':'test'}}]))
    page=history(target,limit=1)
    assert len(page['checkpoints'])==1 and page['nextCursor']
    assert history(target,limit=1,cursor=page['nextCursor'])['checkpoints'][0]['revision']==before
    assert details(target,saved['revision'])['records'][0]['actions'][0]['request']['kind']=='test'
    assert len(compare(target,before,saved['revision'])['files'])==1
    output=materialize(target,before,operation/'historical')
    assert output.name==font.name and source_hash(output)!=source_hash(font)
    assert (root/'unrelated.txt').read_text()=='original\n'
    with pytest.raises(CheckpointError):history(target,limit=101)
    with pytest.raises(CheckpointError):details(target,'HEAD')
    alter(font,'more\n');target.checkpoint(source_hash(font),'another',record())
    with pytest.raises(CheckpointError):history(target,limit=1,cursor=page['nextCursor'])


def test_package_blob_hashing_uses_one_git_process(repo,monkeypatch):
    root,font,_=repo
    if not font.is_dir():return
    for i in range(100):(font/'glyphs'/f'g{i}.glyph').write_text(str(i))
    target,_=engine(repo);original=target.git;calls=[]
    def counted(*args,**kwargs):
        if args[0]=='hash-object':calls.append(args)
        return original(*args,**kwargs)
    monkeypatch.setattr(target,'git',counted)
    target._snapshot(source_hash(font))
    assert len(calls)==1


def test_historical_package_materialization_uses_one_bounded_git_batch(repo,monkeypatch):
    from glyphs_mcp_sidecar.checkpoint_history import materialize
    root,font,operation=repo
    if not font.is_dir():return
    for i in range(100):(font/'glyphs'/f'g{i}.glyph').write_text(str(i))
    target,_=engine(repo)
    receipt=target.checkpoint(source_hash(font),'many_files',record())
    original=target.git;calls=[]
    def counted(*args,**kwargs):
        if args[0]=='cat-file':calls.append(args)
        return original(*args,**kwargs)
    monkeypatch.setattr(target,'git',counted)
    output=materialize(target,receipt['revision'],operation/'materialized')
    assert source_hash(output)==source_hash(font)
    assert calls==[('cat-file','--batch')]
