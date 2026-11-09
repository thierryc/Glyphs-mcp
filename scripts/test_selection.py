"""Conservative development test selection; never a release qualification receipt."""
import ast
from pathlib import Path, PurePosixPath
import subprocess

TEST_ROOT = 'src/glyphs-mcp/tests'
SCOPES = {
    'health': ('*health*', '*task_history*', '*task_expiration*', '*task_archive*',
               '*desktop_activity*', '*desktop_management*', '*document*', '*edit_tabs*', '*task_recovery*', '*task_management*',
               '*workflow_queue*', '*edit_workflow*', '*saved_scripts*', '*script_snapshots*',
               '*script_capacity*', '*python_scripts*', '*compile_export*', '*font_comparison*', '*unified_results*',
               '*bridge_lifecycle*', '*simple_v2_sidecar*'),
    'workflow': ('*simple_v2*workflow*', '*simple_v2*task*', '*simple_v2*script*',
                 '*simple_v2*save*', '*simple_v2*history*', '*simple_v2*document*', '*health*'),
    'skills': ('*skill*', '*codex_plugin*', '*docs*', '*h2_setup_identity*', '*consolidation*'),
    'tooling': ('*development_workflow*', '*readable_test_report*', '*local_release_runner*',
                '*focused_release_scope*', '*python_runtime_matrix*', '*desktop_build*'),
    'desktop': ('*desktop*', '*h2_setup_identity*', '*release_payload*'),
}

# These exercise real external processes, threaded orchestration or packaging.
# They remain in ordinary pytest, component checks, and release qualification.
INTEGRATION_MODULES = frozenset((
    'test_simple_v2_checkpoints', 'test_simple_v2_checkpoint_workflow',
    'test_simple_v2_install', 'test_local_release_runner', 'test_simple_v2_build',
    'test_simple_v2_identity', 'test_simple_v2_saved_scripts', 'test_simple_v2_edit_workflow',
    'test_simple_v2_development', 'test_simple_v2_task_recovery',
    'test_simple_v2_task_management', 'test_simple_v2_unified_results',
    'test_codex_plugin', 'test_desktop_installation', 'test_beta3_installer_payload',
))


def changed_paths(root, base='HEAD'):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args]).decode().split('\0')
    if not base or base.startswith('-'): raise ValueError('Use a commit reference, not a Git option.')
    commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--verify', base + '^{commit}']).decode().strip()
    # HEAD includes staged + unstaged changes. Untracked tests/source also count.
    return sorted(set(filter(None, git('diff', '--name-only', '--no-renames', '-z', commit, '--')
                             + git('ls-files', '--others', '--exclude-standard', '-z'))))


def validate_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or value.startswith('-'):
        raise ValueError('Use repository-relative paths without parent traversal.')
    return path.as_posix()


def select_tests(root, paths=(), *, scope=None):
    root = Path(root)
    available = {p.relative_to(root).as_posix(): p for p in (root / TEST_ROOT).rglob('*.py')
                 if p.name.startswith('test_') or p.name.endswith('_test.py')}
    broad = False
    selected, reasons, native, docs, native_app = set(), [], False, False, False

    def include(group):
        patterns = SCOPES[group]
        selected.update(p for p in available.values() if any(p.match(pattern + '.py') for pattern in patterns))

    if scope:
        if scope not in SCOPES: raise ValueError('Unknown development scope: ' + scope)
        include(scope)
        native = scope == 'desktop'
        native_app = native
        reasons.append('Explicit scope: ' + scope + '; this does not qualify every worktree change.')
    else:
        for raw in paths:
            path = validate_path(raw)
            name = Path(path).name
            if path in available:
                selected.add(available[path])
                reasons.append('Changed test/helper: ' + path)
            elif path.startswith(TEST_ROOT + '/fixtures/'):
                selected.update(available.values())
                broad = True
                reasons.append('Shared test fixture: all Python tests')
            elif path.startswith('macos-installer/'):
                include('desktop'); native = True
                native_app = native_app or '/Sources/' in path or '/Resources/' in path or '.xcodeproj/' in path
                reasons.append('Desktop change: Python contracts and native tests')
            elif path.startswith(('skills/', 'plugins/glyphs-mcp/')):
                include('skills')
                reasons.append('Agent package/skill change')
            elif path.startswith(('content/', 'website/', 'docs/')) or path.endswith('.md'):
                include('skills'); docs = True
                reasons.append('Documentation change')
            elif path.startswith(('src/bridge/', 'src/sidecar/', 'src/protocol/')) and (
                    name.startswith('health') or name in {'task_history.py', 'task_inventory.py', 'task_expiration.py'}):
                include('health')
                reasons.append('Health/history boundary: document, workflow and recovery coverage')
            elif path.startswith(('src/bridge/', 'src/sidecar/')) and name.startswith(('edit_workflow', 'workflow_queue', 'script_')):
                include('workflow'); include('health')
                reasons.append('Workflow/script boundary')
            else:
                selected.update(available.values())
                broad = True
                # Unknown dependencies may affect the desktop and documentation,
                # so component checks broaden all lanes. Fast stays Python-only.
                native = docs = True
                native_app = True
                reasons.append('Shared or unknown input: broad fallback for ' + path)
        if not paths:
            selected.update(available.values())
            broad = True
            reasons.append('No changes found: broad Python smoke, not an empty success')

    # Follow test-to-test helper imports in reverse, transitively. A changed
    # fixture inside test_foo.py can affect tests that import env/setup from it.
    imports = {}
    for path in (() if scope else available.values()):
        try:
            modules = []
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and node.module: modules.append(node.module)
                elif isinstance(node, ast.Import): modules.extend(alias.name for alias in node.names)
            helper_names = {p.name for p in available.values()}
            imports[path] = {name.split('.')[0] + '.py' for name in modules if name.split('.')[0] + '.py' in helper_names}
        except (SyntaxError, OSError):
            selected.update(available.values())
            broad = True
            reasons.append('Unreadable test dependency: broad Python fallback')
    pending = {Path(p).name for p in paths if p in available}
    if scope:
        # Explicit feature checks are deliberately partial. Worktree-wide helper
        # expansion belongs to the default changed-file selection, not to an
        # explicitly requested scope in an otherwise heavily dirty checkout.
        pending.clear()
    visited = set()
    while pending:
        visited.update(pending)
        dependents = {p for p, deps in imports.items() if deps & pending}
        pending = {p.name for p in dependents} - visited
        selected.update(dependents)
    if not selected:
        raise ValueError('Selection is empty; no check may report success without tests.')
    return dict(tests=[TEST_ROOT] if broad else sorted(p.relative_to(root).as_posix() for p in selected), allPython=broad,
                reasons=sorted(set(reasons)), native=native, nativeApp=native_app, docs=docs,
                selectionMode='explicit_scope' if scope else 'worktree_changes')
