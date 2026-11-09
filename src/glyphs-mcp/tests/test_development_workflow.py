"""Selection must fail closed, including new tests and shared fixture imports."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from test_selection import changed_paths, select_tests, validate_path
from dev_checks import python_command, run
from stage_development_payload import stage
from run_desktop_checks import commands


@pytest.fixture
def checkout(tmp_path):
    for name, source in {'test_simple_v2_health.py': '', 'test_health_status_performance.py': '',
                         'test_simple_v2_task_history.py': '', 'test_simple_v2_document_opening.py': '',
                         'test_simple_v2_saved_scripts.py': '', 'test_desktop_activity.py': '',
                         'test_unrelated.py': '', 'test_shared.py': '',
                         'test_consumer.py': 'from test_shared import env\n',
                         'test_transitive.py': 'from test_consumer import env\n'}.items():
        file = tmp_path / 'src/glyphs-mcp/tests' / name
        file.parent.mkdir(parents=True, exist_ok=True); file.write_text(source)
    (tmp_path / '.gitignore').write_text('build/\n')
    (tmp_path / 'source.py').write_text('original')
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Test', '-c',
                    'user.email=test@example.invalid', '-c', 'commit.gpgsign=false',
                    'commit', '-qm', 'Fixture'], check=True)
    return tmp_path


def test_health_selection_covers_the_observed_deadlock_and_growth_boundaries(checkout):
    plan = select_tests(checkout, ['src/sidecar/glyphs_mcp_sidecar/health.py'])
    names = {Path(p).name for p in plan['tests']}
    assert {'test_simple_v2_health.py', 'test_health_status_performance.py',
            'test_simple_v2_task_history.py', 'test_simple_v2_document_opening.py',
            'test_simple_v2_saved_scripts.py'} <= names
    assert 'test_unrelated.py' not in names


def test_new_untracked_tests_are_selected_and_helper_dependents_are_transitive(checkout):
    new = checkout / 'src/glyphs-mcp/tests/test_new_safety.py'
    new.write_text('def test_new_safety(): pass\n')
    helper = checkout / 'src/glyphs-mcp/tests/test_shared.py'; helper.write_text('env = None\n')
    paths = changed_paths(checkout)
    assert new.relative_to(checkout).as_posix() in paths
    selected = {Path(p).name for p in select_tests(checkout, paths)['tests']}
    assert {'test_new_safety.py', 'test_shared.py', 'test_consumer.py', 'test_transitive.py'} <= selected


def test_nested_new_tests_are_selected_without_basename_collisions(checkout):
    new = checkout / 'src/glyphs-mcp/tests/nested/test_simple_v2_health.py'
    new.parent.mkdir(); new.write_text('def test_nested_safety(): pass\n')
    relative = new.relative_to(checkout).as_posix()
    assert relative in select_tests(checkout, changed_paths(checkout))['tests']
    alternate = new.with_name('new_health_test.py'); alternate.write_text('def test_alternate_safety(): pass\n')
    assert alternate.relative_to(checkout).as_posix() in select_tests(checkout, changed_paths(checkout))['tests']
    assert select_tests(checkout, ['unknown.py'])['allPython']


def test_git_option_cannot_hide_unstaged_changes(checkout):
    with pytest.raises(ValueError): changed_paths(checkout, '--cached')


@pytest.mark.parametrize('path', ['src/protocol/glyphs_mcp_protocol/new_contract.py',
                                 'src/glyphs-mcp/tests/fixtures/new.json', 'requirements-dev.txt',
                                 'scripts/unknown_new_builder.py'])
def test_unknown_shared_and_fixture_inputs_fall_back_to_all_python(checkout, path):
    plan = select_tests(checkout, [path])
    assert plan['allPython'] and plan['tests'] == ['src/glyphs-mcp/tests']


def test_mixed_python_and_swift_changes_require_both_components(checkout):
    plan = select_tests(checkout, ['src/bridge/glyphs_mcp_bridge/health.py',
                                 'macos-installer/GlyphsMCPInstaller/Sources/ContentView.swift'])
    assert plan['native']
    assert any('health' in p for p in plan['tests'])
    assert any('desktop' in p for p in plan['tests'])


def test_deleting_a_test_cannot_reduce_the_check_to_an_empty_success(checkout):
    removed = checkout / 'src/glyphs-mcp/tests/test_simple_v2_health.py'; removed.unlink()
    plan = select_tests(checkout, changed_paths(checkout))
    assert plan['allPython'] and plan['tests'] == ['src/glyphs-mcp/tests']


@pytest.mark.parametrize('path', ['../outside.py', '/tmp/outside.py', '-k', ''])
def test_external_paths_and_option_injection_are_rejected(path):
    with pytest.raises(ValueError): validate_path(path)


def test_explicit_scope_is_labeled_partial_and_fast_omits_only_explicit_layers(checkout, tmp_path):
    plan = select_tests(checkout, ['source.py'], scope='health')
    assert plan['selectionMode'] == 'explicit_scope'
    command = python_command(checkout, plan, 'fast', tmp_path)
    assert command[command.index('-m') + 1] == 'not integration and not stress and not dependency'
    assert '--performance-gates' not in command
    assert '--performance-gates' in python_command(checkout, plan, 'performance', tmp_path)
    unrelated_helper = 'src/glyphs-mcp/tests/test_shared.py'
    partial = select_tests(checkout, [unrelated_helper], scope='health')
    assert not any('test_transitive.py' in p for p in partial['tests'])
    (checkout / 'src/glyphs-mcp/tests/test_consumer.py').write_text('from test_simple_v2_saved_scripts import env\n')
    partial = select_tests(checkout, ['src/glyphs-mcp/tests/test_simple_v2_saved_scripts.py'], scope='health')
    assert not any('test_consumer.py' in p for p in partial['tests'])


@pytest.mark.parametrize('failure', ['none', 'python', 'desktop', 'mutation', 'fixture_mutation', 'test_mutation', 'empty', 'skipped', 'failed_evidence'])
def test_reports_require_test_evidence_successful_lanes_and_unchanged_inputs(checkout, failure):
    output = checkout / 'build/check'; output.mkdir(parents=True)
    plan = select_tests(checkout, ['unknown.py'])
    calls = []
    def fake(command, **kwargs):
        name = 'python' if '--pytest' in command else 'desktop' if any('run_desktop_checks' in x for x in command) else 'documentation'
        calls.append(name)
        if name == 'python':
            xml = output / 'python.xml'
            xml.write_text('<testsuite/>' if failure == 'empty' else '<testsuite><testcase name="behavior" time=".01"/></testsuite>')
            if failure in {'skipped', 'failed_evidence'}:
                tag = 'skipped' if failure == 'skipped' else 'failure'
                xml.write_text('<testsuite><testcase name="behavior"><' + tag + '/></testcase></testsuite>')
            if failure == 'mutation': (checkout / 'source.py').write_text('changed')
            if failure == 'fixture_mutation':
                path = checkout / 'src/glyphs-mcp/tests/fixtures/new.json'
                path.parent.mkdir(); path.write_text('{}')
            if failure == 'test_mutation':
                (checkout / 'src/glyphs-mcp/tests/test_simple_v2_health.py').write_text('# changed')
        return NS(returncode=42 if failure == name else 0)
    status = run(checkout, plan, 'component', output, runner=fake)
    report = json.loads((output / 'result.json').read_text())
    assert report['passed'] == (failure == 'none')
    assert (status == 0) == (failure == 'none')
    assert report['qualifiedRelease'] is False
    if failure == 'python': assert calls == ['python']
    assert report['inputsUnchanged'] == (failure not in {'mutation', 'fixture_mutation', 'test_mutation'})


@pytest.fixture
def payload_cache(tmp_path):
    source = tmp_path / 'src/sidecar/module.py'; source.parent.mkdir(parents=True); source.write_text('original')
    runtime = tmp_path / 'runtime'; runtime.mkdir(); (runtime / 'python').write_bytes(b'verified-runtime')
    output = tmp_path / 'build/app/Payload'
    output.parent.mkdir(parents=True)
    builds = []
    def builder(path, **_):
        builds.append(path)
        path.mkdir(exist_ok=True)
        (path / 'bytes').write_bytes(b'verified-payload')
        return {'version': 'fixture'}
    def validate(path):
        if (path / 'bytes').read_bytes() != b'verified-payload': raise ValueError('Tampered payload')
        return {'version': 'fixture'}
    def cached(toolchain='compiler-a'):
        return stage(output, root=tmp_path, runtime=runtime, builder=builder,
                     validator=validate, toolchain=toolchain)
    return tmp_path, output, cached, builds


def test_development_payload_reuses_only_verified_bytes_and_rebuilds_corruption(payload_cache):
    _, output, cached, builds = payload_cache
    assert not cached()['reused']
    assert cached()['reused'] and len(builds) == 1
    (output / 'bytes').write_bytes(b'tampered')
    assert not cached()['reused'] and len(builds) == 2


@pytest.mark.parametrize('changed', ['src/sidecar/module.py', 'skills/example/SKILL.md',
    'third_party/runtime.lock', 'runtime/python', 'runtime/__pycache__/module.pyc', 'scripts/builder.py'])
def test_source_dependency_skill_and_runtime_changes_invalidate_payload_cache(payload_cache, changed):
    root, _, cached, builds = payload_cache
    cached()
    path = root / changed; path.parent.mkdir(parents=True, exist_ok=True)
    # Content changes count even if names, lengths or mtimes could be reused.
    path.write_bytes(b'changed')
    assert not cached()['reused'] and len(builds) == 2


def test_ui_and_test_edits_reuse_payload_but_toolchain_changes_do_not(payload_cache):
    root, _, cached, builds = payload_cache
    cached()
    for name in ['macos-installer/GlyphsMCPInstaller/Sources/View.swift',
                 'src/glyphs-mcp/tests/fixtures/test.json']:
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('changed')
    assert cached()['reused'] and len(builds) == 1
    assert not cached(toolchain='compiler-b')['reused'] and len(builds) == 2


def test_native_development_commands_are_incremental_and_do_not_publish_apps(tmp_path):
    core = commands(tmp_path)
    assert len(core) == 1 and core[0][1] == 'test'
    assert core[0][core[0].index('-scheme') + 1] == 'GlyphsMCPCoreTests'
    assert any('testGeneratedBuildPayloadMatchesSwiftRuntimeIdentity' in arg for arg in core[0])
    app = commands(tmp_path, app=True)
    assert app[0][1] == 'build' and app[1] == core[0]
    assert core[0][core[0].index('-derivedDataPath') + 1] == str(tmp_path / 'build/dev-desktop/DerivedData')
    assert all('dist/local' not in arg for command in app for arg in command)


def test_performance_profile_does_not_rebuild_native_or_docs_for_unrelated_dirty_files(checkout):
    output = checkout / 'build/performance'; output.mkdir(parents=True)
    plan = select_tests(checkout, ['unknown.py'])
    calls = []
    def fake(command, **kwargs):
        calls.append(command)
        (output / 'python.xml').write_text('<testsuite><testcase name="liveness" time=".01"/></testsuite>')
        return NS(returncode=0)
    assert run(checkout, plan, 'performance', output, runner=fake) == 0
    assert len(calls) == 1 and '--performance-gates' in calls[0]


def test_input_snapshot_precedes_selection_and_execution(checkout):
    from release_test_inputs import fingerprint
    output = checkout / 'build/guard'; output.mkdir(parents=True)
    before = fingerprint(checkout)
    plan = select_tests(checkout, [], scope='health')
    (checkout / 'source.py').write_text('changed between selection and execution')
    def fake(*_, **__):
        (output / 'python.xml').write_text('<testsuite><testcase name="behavior"/></testsuite>')
        return NS(returncode=0)
    assert run(checkout, plan, 'fast', output, runner=fake, input_fingerprint=before) != 0
