"""Focused gate for a small stable release against an explicitly qualified baseline."""
import argparse
import json
import plistlib
from pathlib import Path
import re
import subprocess
import sys
from desktop_release_identity import load
from test_selection import changed_paths, select_tests

ROOT = Path(__file__).resolve().parents[1]


def validate_scope(root, base):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True)
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-build\d+)?', base):
        raise ValueError('Use an exact stable release tag as the qualified baseline')
    git('rev-parse', '--verify', base + '^{commit}')
    changed = git('diff', '--name-only', base, '--', 'macos-installer', 'third_party').splitlines()
    changed += git('ls-files', '--others', '--exclude-standard', '--', 'macos-installer', 'third_party').splitlines()
    project = 'macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj'
    info = 'macos-installer/GlyphsMCPInstaller/Info.plist'
    protected = [p for p in changed if p.startswith('third_party/') or
                 (p not in (project, info) and not p.endswith('.md'))]
    if protected:
        raise ValueError('Full qualification required for changed Swift/native/dependency inputs: ' + ', '.join(protected))
    normalize = lambda s: re.sub(r'(MARKETING_VERSION|CURRENT_PROJECT_VERSION)\s*=\s*[^;]+;', r'\1 = VERSION;', s)
    if normalize(git('show', base + ':' + project)) != normalize((root / project).read_text()):
        raise ValueError('Full qualification required for Xcode configuration changes beyond version/build')
    original = plistlib.loads(git('show', base + ':' + info).encode())
    current = plistlib.loads((root / info).read_bytes())
    for metadata in (original, current):
        for key in ('CFBundleDisplayName', 'GMCPReleaseChannel', 'GMCPBetaNumber', 'SUFeedURL', 'GMCPTemplateRegistryURL'):
            metadata.pop(key, None)
    if original != current:
        raise ValueError('Full qualification required for application metadata beyond release labels/feeds')
    return {'baseline': base, 'swiftImplementationUnchanged': True, 'dependencyInputsUnchanged': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-ref', required=True)
    args = parser.parse_args()
    scope = validate_scope(ROOT, args.base_ref)
    release = load(ROOT)
    if release['channel'] != 'stable':
        raise ValueError('Focused stable gate requires stable release metadata')
    subprocess.run(['bash', 'scripts/sync_codex_plugin_skills.sh', '--check'], cwd=ROOT, check=True)
    subprocess.run([sys.executable, 'scripts/check_lean_package.py'], cwd=ROOT, check=True)
    tests = ['test_simple_v2_saved_scripts.py', 'test_simple_v2_script_snapshots.py',
             'test_simple_v2_path_cleanup.py', 'test_simple_v2_path_doctor.py',
             'test_simple_v2_outline_edit.py', 'test_simple_v2_edit_workflow.py',
             'test_simple_v2_edit_workflow_ui.py', 'test_simple_v2_sidecar.py',
             'test_simple_v2_bridge.py', 'test_simple_v2_protocol.py',
             'test_simple_v2_exact_history.py', 'test_skill_catalog_package.py',
             'test_simple_v2_skill_routing.py',
             'test_simple_v2_python_scripts.py', 'test_curve_repair_actions.py', 'test_curve_repair_controller.py',
             'test_simple_v2_build.py::test_build_is_deterministic_and_excludes_the_old_runtime',
             'test_simple_v2_identity.py::test_packaged_runtime_matches_manifest_then_keeps_initialization_fingerprint']
    # Retain the qualified baseline checks, then add coverage for every changed
    # input. Unknown/shared inputs broaden the suite rather than silently omitting
    # newly introduced features such as health and history contention.
    selection = select_tests(ROOT, changed_paths(ROOT, args.base_ref))
    tests = selection['tests'] if selection['allPython'] else sorted(set(['src/glyphs-mcp/tests/' + p for p in tests] + selection['tests']))
    subprocess.run([sys.executable, '-m', 'pytest', '-q', *tests, '--performance-gates'], cwd=ROOT, check=True)
    from release_test_inputs import fingerprint
    report = {'profile': 'focused', 'release': release, 'scope': scope, 'testSelection': selection, 'sourceFingerprint': fingerprint(ROOT),
              'limitations': 'No full Swift suite or VM matrix; signing, notarization and final artifact verification remain mandatory.'}
    (ROOT / 'build/focused-release-tests.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
