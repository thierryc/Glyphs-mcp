"""Whole-installation recovery, including a process interrupted between renames."""
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'scripts'))
from installation_transaction import InstallationTransaction


@pytest.mark.parametrize('failure', range(4))
def test_every_replacement_failure_restores_all_previous_files(tmp_path, monkeypatch, failure):
    old, source, journal = [tmp_path / n for n in ('installed', 'source', 'transactions')]
    for path in (old, source, journal): path.mkdir()
    changes = []
    for index in range(4):
        (old/str(index)).write_text('old'); (source/str(index)).write_text('new')
        changes.append((source/str(index), old/str(index)))
    transaction = InstallationTransaction(journal, changes)
    rename = Path.rename
    def fail_once(path, destination):
        if path == transaction.stage / str(failure):
            raise OSError('simulated replacement failure')
        return rename(path, destination)
    monkeypatch.setattr(Path, 'rename', fail_once)
    with pytest.raises(OSError): transaction.apply()
    assert [p.read_text() for p in sorted(old.iterdir())] == ['old'] * 4
    assert json.loads(transaction.journal.read_text())['state'] == 'restored'


def test_failed_verification_restores_files_removals_and_new_install(tmp_path):
    old = tmp_path/'old'; old.write_text('original')
    source = tmp_path/'source'; source.write_text('new')
    new = tmp_path/'new'
    transaction = InstallationTransaction(tmp_path, [(None, old), (source, new)])
    with pytest.raises(RuntimeError, match='health'):
        transaction.apply(lambda: (_ for _ in ()).throw(RuntimeError('health failed')))
    assert old.read_text() == 'original' and not new.exists()


def test_recover_after_process_stops_between_backup_and_install(tmp_path):
    target = tmp_path/'plugin'; target.write_text('original')
    source = tmp_path/'source'; source.write_text('replacement')
    transaction = InstallationTransaction(tmp_path, [(source, target)])
    transaction.data.update(state='applying')
    transaction.data['entries'][0]['started'] = True
    transaction.journal.write_text(json.dumps(transaction.data))
    target.rename(transaction.backup/target.name)
    InstallationTransaction.recover(tmp_path, {target})
    assert target.read_text() == 'original'
    InstallationTransaction.recover(tmp_path, {target})
    assert target.read_text() == 'original'


def test_interrupted_install_retains_server_running_intent_for_recovery(tmp_path):
    target=tmp_path/'agent.plist';target.write_text('previous agent')
    source=tmp_path/'new';source.write_text('replacement')
    transaction=InstallationTransaction(tmp_path,[(source,target)])
    transaction.data.update(state='applying',launchAgentWasLoaded=True)
    transaction.data['entries'][0]['started']=True
    transaction.journal.write_text(json.dumps(transaction.data))
    target.rename(transaction.backup/target.name)
    recovered=InstallationTransaction.recover(tmp_path,{target})
    assert recovered[0]['launchAgentWasLoaded'] is True
    assert target.read_text()=='previous agent'
    assert InstallationTransaction.recover(tmp_path,{target})==[]
