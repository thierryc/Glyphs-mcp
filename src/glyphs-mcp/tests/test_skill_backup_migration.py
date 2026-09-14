import sys,json,hashlib
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
from archive_skill_backups import archive,restore,hashes

def test_explicit_backup_relocation_and_exact_restore(tmp_path):
 root=tmp_path/'skills';old=root/'glyphs.bak-20260910-123456';old.mkdir(parents=True)
 (old/'SKILL.md').write_bytes(b'user work\x00\n');(old/'hidden').write_bytes(b'policy')
 unknown=root/'my-backup';unknown.mkdir();(unknown/'SKILL.md').write_text('leave me')
 evidence={str(old):{str(old/k):v for k,v in hashes(old).items()}}
 plan=archive(root,evidence);assert old.exists() and plan['state']=='planned'
 result=archive(root,evidence,apply=True);assert not old.exists() and unknown.exists()
 assert not Path(result['items'][0]['backup']).is_relative_to(root)
 assert restore(result['receipt'])['restored'];assert hashes(old)==result['items'][0]['hashes']
 with pytest.raises(ValueError):restore(result['receipt'])

def test_mismatched_or_symlink_evidence_does_not_move(tmp_path):
 root=tmp_path/'skills';old=root/'glyphs.bak-20260910-123456';old.mkdir(parents=True)
 (old/'SKILL.md').write_text('edited')
 with pytest.raises(ValueError):archive(root,{str(old):{str(old/'SKILL.md'):'wrong'}},apply=True)
 assert old.exists() and not (tmp_path/'glyphs-mcp-skill-backups').exists()
 (old/'link').symlink_to(old/'SKILL.md')
 with pytest.raises(ValueError):hashes(old)
