"""Exercise the real shell orchestration with isolated deterministic fake tools."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

REPO = Path(__file__).resolve().parents[3]


def executable(path, text):
    path.write_text(text)
    path.chmod(0o755)


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / 'repo'
    scripts = root / 'scripts'
    scripts.mkdir(parents=True)
    (root / 'website').mkdir()
    (root / 'build').mkdir()
    (root / '.gitignore').write_text('build/\n')
    (root / 'source.txt').write_text('original')
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=/dev/null', 'commit', '-q', '--allow-empty', '-m', 'fixture'], check=True)
    for name in ('run_local_release_tests.sh', 'release_test_inputs.py'):
        shutil.copy2(REPO / 'scripts' / name, scripts / name)
    # The preflight syntax check still opens and parses every listed script.
    for name in ('build_installer_app.sh', 'build_desktop_release.sh', 'notarize_installer_app.sh', 'make_installer_dmg.sh',
                 'render_dmg_background.sh', 'publish_release_assets.sh', 'verify_release_artifacts.sh',
                 'sync_codex_plugin_skills.sh'):
        executable(scripts / name, '#!/bin/bash\nexit 0\n')
    tool = root / 'fake_tool.py'
    executable(tool, f'#!{sys.executable}\n' + r'''
import os, pathlib, subprocess, sys, time
root = pathlib.Path(os.environ['FAKE_ROOT'])
args = sys.argv[1:]
name = pathlib.Path(args[0]).name if args else ''
if name == 'release_test_inputs.py':
    raise SystemExit(subprocess.call([sys.executable, str(root/'scripts'/name)]))
if name == 'desktop_release_identity.py':
    print({'version':'2.0.2','installerBuild':'57','betaNumber':'0'}[args[-1]])
elif name == 'build_installer_payload.py':
    output = pathlib.Path(args[args.index('--output-root')+1]); output.mkdir()
    (output/'manifest').write_text('same')
elif name in ('python-lane', 'desktop-lane', 'documentation-lane'):
    lane = name.removesuffix('-lane')
    with (root/'build'/f'{lane}.started').open('w') as stream: stream.write('ready')
    (root/'build'/f'{lane}.pid').write_text(str(os.getpid()))
    if os.environ.get('FAKE_BLOCK') == '1': time.sleep(30)
    if os.environ.get('FAKE_PARALLEL') == '1':
        deadline = time.monotonic() + 10
        while len(list((root/'build').glob('*.started'))) < 3:
            if time.monotonic() > deadline: raise SystemExit('lanes did not overlap')
            time.sleep(.02)
    with (root/'build'/'order').open('a') as stream: stream.write(lane+'\n')
    if lane == 'python':
        assert os.environ['GLYPHS_MCP_FULL_PYTHON_MATRIX'] == '1'
        if os.environ.get('FAKE_MUTATE') == '1': (root/'source.txt').write_text('changed')
    if lane == 'desktop':
        assert 'test' in args and 'build' not in args
        output = pathlib.Path(args[args.index('-derivedDataPath')+1])/'Build/Products/Debug/Glyphs MCP.app'
        output.mkdir(parents=True)
    if os.environ.get('FAKE_FAIL') == lane: raise SystemExit(42)
elif name == 'verify_desktop_app.py':
    assert pathlib.Path(args[1]).is_dir()
    (root/'build'/'app-verified').write_text('yes')
elif name == 'release_security.py':
    (root/'build'/'candidate-verified').write_text('yes')
''')
    executable(scripts / 'run_python_tests.sh', '#!/bin/bash\nexec "$PYTHON_BIN" python-lane "$@"\n')
    binary = root / 'bin'
    binary.mkdir()
    executable(binary / 'xcodebuild', f'#!/bin/bash\nexec "{tool}" desktop-lane "$@"\n')
    executable(binary / 'npm', f'#!/bin/bash\nexec "{tool}" documentation-lane "$@"\n')
    env = dict(os.environ, FAKE_ROOT=str(root), PYTHON_BIN=str(tool),
               PATH=str(binary)+os.pathsep+os.environ['PATH'])
    return root, env


def run(checkout, *args, **variables):
    root, env = checkout
    env.update(variables)
    return subprocess.run(['/bin/bash', str(root/'scripts/run_local_release_tests.sh'), *args],
                          env=env, text=True, capture_output=True, timeout=25)


def test_parallel_full_lanes_share_no_build_outputs(checkout):
    result = run(checkout, FAKE_PARALLEL='1')
    assert result.returncode == 0, result.stdout + result.stderr
    root, _ = checkout
    assert (root/'build/app-verified').exists()
    assert (root/'build/candidate-verified').exists()
    assert len(list((root/'build').glob('release-test-run.*/inputs.sha256'))) == 1
    assert not (root/'build/release-tests.lock').exists()


def test_serial_mode_runs_the_same_three_lanes(checkout):
    result = run(checkout, '--serial')
    assert result.returncode == 0, result.stdout + result.stderr
    root, _ = checkout
    assert (root/'build/order').read_text().splitlines() == ['python', 'desktop', 'documentation']


def test_failed_desktop_tests_cannot_be_hidden_by_valid_app(checkout):
    result = run(checkout, FAKE_PARALLEL='1', FAKE_FAIL='desktop')
    assert result.returncode != 0
    root, _ = checkout
    assert not (root/'build/candidate-verified').exists()
    assert not (root/'build/app-verified').exists()
    assert not list((root/'build').glob('release-test-run.*/inputs.sha256'))
    assert 'failed' in result.stderr.lower()


def test_edit_during_test_run_invalidates_acceptance(checkout):
    result = run(checkout, FAKE_PARALLEL='1', FAKE_MUTATE='1')
    assert result.returncode != 0
    root, _ = checkout
    assert not list((root/'build').glob('release-test-run.*/inputs.sha256'))
    assert 'inputs changed' in result.stderr


def test_overlapping_gate_is_rejected_without_removing_owner_lock(checkout):
    root, _ = checkout
    lock = root/'build/release-tests.lock'
    lock.mkdir()
    (lock/'pid').write_text('12345')
    result = run(checkout)
    assert result.returncode != 0
    assert (lock/'pid').read_text() == '12345'


def test_fingerprint_detects_deletion_and_untracked_source_but_ignores_build(checkout):
    root, _ = checkout
    spec = importlib.util.spec_from_file_location('release_inputs', REPO/'scripts/release_test_inputs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    before = module.fingerprint(root)
    (root/'build/generated').write_text('output')
    assert module.fingerprint(root) == before
    (root/'source.txt').unlink()
    assert module.fingerprint(root) != before
    after = module.fingerprint(root)
    (root/'new.txt').write_text('new source')
    assert module.fingerprint(root) != after


@pytest.mark.parametrize('lane', ['python', 'documentation'])
def test_other_lane_failures_block_candidate_acceptance(checkout, lane):
    result = run(checkout, FAKE_PARALLEL='1', FAKE_FAIL=lane)
    assert result.returncode != 0
    root, _ = checkout
    assert not (root/'build/candidate-verified').exists()
    assert not list((root/'build').glob('release-test-run.*/inputs.sha256'))


def test_interrupt_terminates_lanes_and_never_records_success(checkout):
    root, env = checkout
    env = dict(env, FAKE_BLOCK='1')
    process = subprocess.Popen(['/bin/bash', str(root/'scripts/run_local_release_tests.sh')],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    completed = False
    try:
        deadline = time.monotonic() + 15
        while len(list((root/'build').glob('*.started'))) < 3:
            assert time.monotonic() < deadline
            time.sleep(.05)
        process.terminate()
        process.communicate(timeout=5)
        completed = True
        assert process.returncode != 0
        assert not list((root/'build').glob('release-test-run.*/inputs.sha256'))
        assert not (root/'build/release-tests.lock').exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if not completed:
            for path in (root/'build').glob('*.pid'):
                try: os.kill(int(path.read_text()), 9)
                except ProcessLookupError: pass
