"""Reject stale or incomplete desktop apps before they become install candidates."""
import json
import hashlib
from pathlib import Path
import plistlib
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts'))
import verify_desktop_app as verifier
import clean_desktop_builds as cleaner
import build_local_app as builder
import prepare_desktop_dependencies as dependencies


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    app = tmp_path / 'Glyphs MCP.app'
    info = {'CFBundleIdentifier': 'cx.ap.glyphsMcp', 'CFBundleShortVersionString': '2.0.0',
            'CFBundleVersion': '43', 'CFBundleExecutable': 'Glyphs MCP'}
    for name in ['Contents/MacOS/Glyphs MCP', 'Contents/Resources/Assets.car',
                 'Contents/Frameworks/Sparkle.framework/Sparkle',
                 'Contents/Frameworks/GlyphsMCPInstallerCore.framework/GlyphsMCPInstallerCore']:
        path = app / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture')
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    resources = app / 'Contents/Resources/PierreDiffsSwift_PierreDiffsSwift.bundle/Contents/Resources/Resources'
    resources.mkdir(parents=True)
    pierre_resources = {'diff-core.js': b'fixture-normal', 'diff-core-edit.js': b'fixture-edit'}
    for name, data in pierre_resources.items():
        (resources / name).write_bytes(data)
    lock = {'version': '1.2.4', 'commit': 'c2249d7890de957a96480711152d90a06fa1222b',
            'resources': {name: hashlib.sha256(data).hexdigest()
                          for name, data in pierre_resources.items()}}
    lock_path = tmp_path / 'third_party/pierre-diffs-swift.json'
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(json.dumps(lock))
    catalog = tmp_path / 'macos-installer/GlyphsMCPInstaller/Resources/Assets.xcassets'
    for name in ['GlyphsMCPMenu', 'GitHubMark']:
        (catalog / (name + '.imageset')).mkdir(parents=True)
    monkeypatch.setattr(verifier, 'load', lambda root: {'version': '2.0.0', 'installerBuild': 43})
    monkeypatch.setattr(verifier.subprocess, 'check_output', lambda command: json.dumps([
        {'Name': 'GlyphsMCPMenu'}, {'Name': 'GitHubMark'}]).encode())
    return app, tmp_path


def test_rejects_old_asset_catalog_even_when_version_and_executable_match(bundle, monkeypatch):
    app, root = bundle
    monkeypatch.setattr(verifier.subprocess, 'check_output', lambda command: b'[{"Name":"AppIcon"}]')
    with pytest.raises(ValueError, match='Missing compiled assets: GitHubMark, GlyphsMCPMenu'):
        verifier.verify(app, root)


def test_new_source_asset_must_be_in_compiled_catalog(bundle):
    app, root = bundle
    (root / 'macos-installer/GlyphsMCPInstaller/Resources/Assets.xcassets/NewIcon.imageset').mkdir()
    with pytest.raises(ValueError, match='NewIcon'):
        verifier.verify(app, root)


def test_rejects_wrong_build(bundle):
    app, root = bundle
    path = app / 'Contents/Info.plist'
    info = plistlib.loads(path.read_bytes())
    info['CFBundleVersion'] = '42'
    path.write_bytes(plistlib.dumps(info))
    with pytest.raises(ValueError, match='CFBundleVersion'):
        verifier.verify(app, root)


def test_rejects_missing_linked_framework(bundle):
    app, root = bundle
    (app / 'Contents/Frameworks/Sparkle.framework/Sparkle').unlink()
    with pytest.raises(ValueError, match='Missing linked framework: Sparkle'):
        verifier.verify(app, root)


def test_rejects_missing_pierre_resource_bundle(bundle):
    app, root = bundle
    resource = app / 'Contents/Resources/PierreDiffsSwift_PierreDiffsSwift.bundle/Contents/Resources/Resources/diff-core.js'
    resource.unlink()
    with pytest.raises(ValueError, match='Missing PierreDiffsSwift JavaScript resource'):
        verifier.verify(app, root)


def test_rejects_modified_pierre_javascript(bundle):
    app, root = bundle
    resource = app / 'Contents/Resources/PierreDiffsSwift_PierreDiffsSwift.bundle/Contents/Resources/Resources/diff-core.js'
    resource.write_bytes(b'modified')
    with pytest.raises(ValueError, match='PierreDiffsSwift JavaScript identity mismatch'):
        verifier.verify(app, root)


def test_pierre_hardening_patch_is_exact_and_idempotence_is_rejected(tmp_path):
    root = tmp_path / 'PierreDiffsSwift'
    files = {
        'Sources/PierreDiffsSwift/WebView/PierreDiffView.swift':
            '    let configuration = WKWebViewConfiguration()\n'
            '    configuration.preferences.setValue(true, forKey: "developerExtrasEnabled")\n',
        'Sources/PierreDiffsSwift/WebView/DiffHTMLTemplate.swift':
            '        <meta charset="UTF-8">\n',
        'Sources/PierreDiffsSwift/WebView/DiffWebViewCoordinator.swift':
            'extension DiffWebViewCoordinator: WKNavigationDelegate {\n\n',
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    dependencies.apply_pierre_local_only_patch(root)
    combined = '\n'.join((root / relative).read_text() for relative in files)
    assert 'websiteDataStore = .nonPersistent()' in combined
    assert 'developerExtrasEnabled")' in combined and 'setValue(false' in combined
    assert 'Content-Security-Policy' in combined
    assert 'scheme == nil || scheme == "about"' in combined
    with pytest.raises(ValueError, match='patch context changed'):
        dependencies.apply_pierre_local_only_patch(root)


def test_glyph_svg_renderer_is_delta_only_local_and_read_only():
    source = (Path(__file__).resolve().parents[3]
              / 'macos-installer/GlyphsMCPInstaller/Sources/DesktopGitWorkspace.swift').read_text()
    service = (Path(__file__).resolve().parents[3]
               / 'macos-installer/GlyphsMCPInstaller/Core/GlyphDiff.swift').read_text()
    assert 'configuration.websiteDataStore = .nonPersistent()' in source
    assert 'allowsContentJavaScript = true' in source
    assert 'WKContentWorld.world(name: "GlyphDiffCamera")' in source
    assert "script-src 'none'" in source
    assert 'scheme == nil || scheme == "about" ? .allow : .cancel' in source
    assert 'evaluateJavaScript' not in source
    assert 'callAsyncJavaScript' in source
    assert 'requestAnimationFrame(apply)' in source
    assert 'magnification: state.magnification, final: force' in source
    assert 'if final || abs(zoomBinding.wrappedValue - magnification) >= 0.005' in source
    assert 'webView.setMagnification' not in source
    assert '.fixed-control{transform-box:fill-box' in source
    assert 'let signature = "\\(viewportKey):\\(String(reflecting: layer)):\\(fullViewBox)"' in source
    assert '"setPresentation"' in source
    assert '"setFillPreview"' in source
    assert '"setCamera"' in source
    assert '"smoothZoom"' in source
    assert 'body["key"] as? String == viewportKey' in source
    assert 'GlyphViewportMath.isRestorable(state, in: fullViewBox)' in source
    assert source.count("<path class='delta'") == 1
    assert "fill-rule:evenodd" in source
    assert ".neutral{fill:none;stroke:" in source
    assert "if value.outlineChanged" in source
    assert "visible('delta-fill', both)" in source
    assert "visible('after-neutral', payload.overlay === 'after' || (both && payload.hasAfter))" in source
    assert "guard zoomToolActive else" in source
    assert '.smoothZoom(-delta, canvasPoint(event))' in source
    assert '.pan(CGPoint(x: -event.scrollingDeltaX, y: -event.scrollingDeltaY))' in source
    assert '--outline-stroke:.5;--delta-stroke:.65;--detail-stroke:.25;' in source
    assert '.neutral{fill:none;stroke:var(--neutral);stroke-width:var(--outline-stroke);' in source
    assert '.reference-change{fill:none;stroke:#3fe2a6;stroke-width:var(--delta-stroke);' in source
    assert '.delta{fill:#3fd1e25c;stroke:none;fill-rule:evenodd}' in source
    assert '.width-change{fill:#3fd1e25c}' in source
    assert '.current-change{fill:none;stroke:#3fd1e2;stroke-width:var(--delta-stroke);' in source
    assert "class='origin-advance advance guide-dependent' x1='0'" in source
    assert '.origin-advance{stroke:var(--guide);stroke-width:1.25;stroke-dasharray:6 4;' in source
    assert "class='neutral advance guide-dependent' x1='0'" not in source
    assert '.neutral-handle{stroke:var(--handle);stroke-width:var(--detail-stroke);' in source
    assert '.current-handle{stroke:var(--handle)}' in source
    assert '.neutral-node,.neutral-control{fill:none;stroke:var(--control);' in source
    assert '.current-node,.current-control{fill:none;stroke:var(--control);' in source
    assert 'control: colorScheme == .dark ? "#a8a8a8" : "#858585"' in source
    assert 'handle: colorScheme == .dark ? "#707070" : "#b8b8b8"' in source
    assert "style.setProperty('--control', payload.control)" in source
    assert "style.setProperty('--handle', payload.handle)" in source
    assert '.fill-preview path.neutral:not(.open){fill:#000;stroke:#000}' in source
    assert '.fill-preview #delta-fill' in source
    assert 'event.charactersIgnoringModifiers == " "' in source
    assert 'actionHandler?(.fillPreview(true))' in source
    assert 'actionHandler?(.fillPreview(false))' in source
    assert "svg.classList.toggle('fill-preview', payload.active)" in source
    assert "value[0]-3.5" in source and "width='7' height='7'" in source
    assert "r='3'" in source
    assert ".neutral-node,.neutral-control{fill:none;" in source
    assert ".reference-node,.reference-control{fill:none;" in source
    assert ".current-node,.current-control{fill:none;" in source
    assert "class='fixed-position-label fixed-guide-label' data-x='\\(maxX)' data-y='\\(-value)'" in source
    assert "class='fixed-position-label fixed-anchor-label'" in source
    assert 'let payload = try? InstallerPayload.resolve()' in service
    assert 'GlyphDiffRuntime.resolve(extractedPayloadURL: payload?.payloadDir)' in service
    assert 'let labelX = css == "reference" ? -8 : 8' in source
    assert 'let labelY = css == "reference" ? -8 : 14' in source
    assert ".reference-change.anchor-label{fill:#3fe2a6;stroke:none;text-anchor:end}" in source
    assert ".current-change.anchor-label{fill:#3fd1e2;stroke:none;text-anchor:start}" in source
    assert ".label{fill:var(--guide);font:500 12px -apple-system" in source


def test_diff_loading_states_explain_work_without_repeated_accessibility_announcements():
    source = (Path(__file__).resolve().parents[3]
              / 'macos-installer/GlyphsMCPInstaller/Sources/DesktopGitWorkspace.swift').read_text()
    assert 'DiffLoadingView.comparison(includesGlyphGeometry: change.isGlyphPackageGlyph)' in source
    assert 'DiffLoadingView.glyphGeometry' in source
    assert 'Reading the reference version from Git…' in source
    assert 'Comparing HEAD with the working tree…' in source
    assert 'Loading layers and decomposing components…' in source
    assert 'Comparing outlines, anchors, and widths…' in source
    assert 'Preparing the interactive visual diff…' in source
    assert 'try await Task.sleep(for: .seconds(1.8))' in source
    assert 'withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.3))' in source
    assert '.accessibilityElement(children: .ignore)' in source
    assert '.accessibilityLabel(accessibilityStatus)' in source
    assert "document.querySelectorAll('.fixed-position-label')" in source
    assert "Math.hypot(matrix.a, matrix.b)" in source
    assert "const inverse = 1 / (z * displayScale())" in source
    assert "translate(${item.x} ${item.y}) scale(${inverse})" in source
    assert "new ResizeObserver(schedule).observe(svg)" in source


def test_desktop_layout_minimums_keep_navigation_and_diff_controls_visible():
    root = Path(__file__).resolve().parents[3]
    content = (root / 'macos-installer/GlyphsMCPInstaller/Sources/ContentView.swift').read_text()
    delegate = (root / 'macos-installer/GlyphsMCPInstaller/Sources/DesktopAppDelegate.swift').read_text()
    git_workspace = (root / 'macos-installer/GlyphsMCPInstaller/Sources/DesktopGitWorkspace.swift').read_text()
    assert 'static let minimumWidth: CGFloat = 1_040' in content
    assert 'static let sidebarMinimumWidth: CGFloat = 220' in content
    assert '.frame(maxWidth: .infinity, alignment: .leading)' in content
    assert 'static let contentMaximumWidth: CGFloat = 850' in content
    assert '.frame(maxWidth: DesktopOverviewLayout.contentMaximumWidth, alignment: .leading)' in content
    assert '.frame(maxWidth: .infinity, alignment: .center)' in content
    assert '.frame(maxWidth: .infinity, maxHeight: .infinity)' in content
    assert 'window.contentMinSize = NSSize(width: DesktopDashboardLayout.minimumWidth' in delegate
    assert '.frame(minWidth: 220, idealWidth: 260, maxWidth: 380' in git_workspace
    assert 'ViewThatFits(in: .horizontal)' in git_workspace
    assert '.frame(minWidth: 140, idealWidth: 175, maxWidth: 190)' in git_workspace
    assert '.pickerStyle(.segmented).labelsHidden().frame(width: 170)' in git_workspace
    assert 'Toggle("Guides", isOn: $guides).toggleStyle(.checkbox).fixedSize()' in git_workspace
    assert '.frame(minWidth: 500, maxWidth: .infinity' in git_workspace
    assert '.toggleStyle(.checkbox).fixedSize()' in git_workspace


@pytest.mark.parametrize('change', ['source', 'worktree', 'app', 'none'])
def test_receipt_binds_app_to_worktree_and_source(bundle, monkeypatch, change):
    app, root = bundle
    monkeypatch.setattr(verifier, 'source_digest', lambda root: 'source-1')
    receipt = root / 'receipt.json'
    receipt.write_text(json.dumps({'sourceRoot': str(root), 'sourceSHA256': 'source-1',
                                   'bundle': verifier.verify(app, root)}))
    if change == 'source':
        monkeypatch.setattr(verifier, 'source_digest', lambda root: 'source-2')
    elif change == 'worktree':
        data = json.loads(receipt.read_text())
        data['sourceRoot'] = '/another/worktree'
        receipt.write_text(json.dumps(data))
    elif change == 'app':
        (app / 'Contents/MacOS/Glyphs MCP').write_bytes(b'old binary with same version')
    if change == 'none':
        assert verifier.verify_receipt(app, receipt, root)['build'] == '43'
    else:
        with pytest.raises(ValueError, match='receipt'):
            verifier.verify_receipt(app, receipt, root)


def test_cleanup_preserves_source_worktree_even_inside_known_output(tmp_path, monkeypatch):
    monkeypatch.setattr(cleaner.subprocess, 'check_output', lambda command: b'')
    nested = tmp_path / 'build/xcode/source'
    nested.mkdir(parents=True)
    (nested / '.git').write_text('gitdir: elsewhere')
    with pytest.raises(ValueError, match='source worktree'):
        cleaner.clean(tmp_path, apply=True)
    assert (nested / '.git').exists()


def test_cleanup_refuses_tracked_files(tmp_path, monkeypatch):
    monkeypatch.setattr(cleaner.subprocess, 'check_output', lambda command: b'build/xcode/source.swift')
    (tmp_path / 'build/xcode').mkdir(parents=True)
    with pytest.raises(ValueError, match='tracked files'):
        cleaner.clean(tmp_path, apply=True)


def test_cleanup_refuses_redirected_output(tmp_path):
    (tmp_path / 'build').mkdir()
    (tmp_path / 'source').mkdir()
    (tmp_path / 'build/xcode').symlink_to(tmp_path / 'source', target_is_directory=True)
    with pytest.raises(ValueError, match='redirected output'):
        cleaner.clean(tmp_path, apply=True)


def test_cleanup_removes_only_generated_outputs_and_retains_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(cleaner.subprocess, 'check_output', lambda command: b'')
    output = tmp_path / 'build/xcode'
    output.mkdir(parents=True)
    (output / 'Assets.car').write_bytes(b'old assets')
    retained = tmp_path / 'build/source-worktree'
    retained.mkdir()
    (retained / '.git').write_text('gitdir: elsewhere')
    assert cleaner.clean(tmp_path)['bytes'] == 10
    assert output.exists()
    result = cleaner.clean(tmp_path, apply=True)
    assert not output.exists()
    assert (retained / '.git').exists()
    assert Path(result['receipt']).exists()


def test_failed_build_invalidates_old_candidate_and_cleans_temporary_directory(tmp_path, monkeypatch):
    import subprocess
    output = tmp_path / 'dist/local'
    (output / 'Glyphs MCP.app').mkdir(parents=True)
    (output / 'build-receipt.json').write_text('old receipt')
    monkeypatch.setattr(builder, 'ROOT', tmp_path)
    monkeypatch.setattr(builder, 'source_digest', lambda: 'source')
    def run(command, **kwargs):
        if command[0] == 'xcodebuild':
            raise subprocess.CalledProcessError(65, command)
    monkeypatch.setattr(builder.subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        builder.build()
    assert not (output / 'build-receipt.json').exists()
    assert not (output / 'Glyphs MCP.app').exists()
    assert not list((tmp_path / 'build/local-app-runs').iterdir())
