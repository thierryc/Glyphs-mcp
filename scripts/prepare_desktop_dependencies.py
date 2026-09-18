#!/usr/bin/env python3
"""Prepare checksum-pinned desktop dependencies for local builds."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
from urllib.request import urlopen
from build_simple_v2 import _identity

ROOT = Path(__file__).resolve().parents[1]


def prepare(archive=None):
    lock = json.loads((ROOT/'third_party/sparkle.json').read_text())
    cache = ROOT/'build/desktop-dependencies'; cache.mkdir(parents=True, exist_ok=True)
    archive = Path(archive) if archive else cache/('Sparkle-'+lock['version']+'.tar.xz')
    if not archive.exists():
        with urlopen(lock['url'], timeout=60) as response:
            data = response.read(32 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != lock['sha256']: raise ValueError('Sparkle archive checksum mismatch')
        archive.write_bytes(data)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['sha256']: raise ValueError('Sparkle archive checksum mismatch')
    marker = cache/'verified-sparkle.json'
    sparkle_ready = False
    if marker.exists() and (cache/'Sparkle.framework').is_dir():
        previous = json.loads(marker.read_text())
        if previous.get('lock') == lock and previous.get('identities') == {name: _identity(cache/name) for name in ('Sparkle.framework', 'bin')}:
            sparkle_ready = True
    if not sparkle_ready:
        with tempfile.TemporaryDirectory(prefix='sparkle-', dir=cache) as temporary:
            with tarfile.open(archive) as stream: stream.extractall(temporary, filter='data')
            for name in ('Sparkle.framework', 'bin', 'LICENSE'):
                target = cache/name
                if target.is_dir(): shutil.rmtree(target)
                elif target.exists(): target.unlink()
                source = Path(temporary)/name
                if source.is_dir(): shutil.copytree(source, target, symlinks=True)
                else: shutil.copy2(source, target)
        marker.write_text(json.dumps({'lock': lock, 'identities': {name: _identity(cache/name) for name in ('Sparkle.framework', 'bin')}}, sort_keys=True, indent=2)+'\n')
    prepare_pierre(cache)
    return cache


def prepare_pierre(cache):
    lock = json.loads((ROOT/'third_party/pierre-diffs-swift.json').read_text())
    patch = ROOT/'third_party/patches/pierre-diffs-swift-local-only.patch'
    patch_sha256 = hashlib.sha256(patch.read_bytes()).hexdigest()
    archive = cache/('PierreDiffsSwift-'+lock['version']+'.tar.gz')
    if not archive.exists():
        with urlopen(lock['url'], timeout=60) as response:
            data = response.read(32 * 1024 * 1024)
        if hashlib.sha256(data).hexdigest() != lock['sha256']:
            raise ValueError('PierreDiffsSwift archive checksum mismatch')
        archive.write_bytes(data)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != lock['sha256']:
        raise ValueError('PierreDiffsSwift archive checksum mismatch')
    target = cache/'PierreDiffsSwift'
    marker = cache/'verified-pierre-diffs-swift.json'
    if marker.exists() and (target/'Package.swift').is_file():
        previous = json.loads(marker.read_text())
        if (previous.get('lock') == lock and previous.get('patchSHA256') == patch_sha256
                and previous.get('identity') == _identity(target)):
            return
    with tempfile.TemporaryDirectory(prefix='pierre-', dir=cache) as temporary:
        with tarfile.open(archive) as stream:
            stream.extractall(temporary, filter='data')
        roots = [item for item in Path(temporary).iterdir() if item.is_dir()]
        if len(roots) != 1 or not (roots[0]/'Package.swift').is_file():
            raise ValueError('PierreDiffsSwift archive layout is invalid')
        staged = cache/'PierreDiffsSwift.staged'
        if staged.exists(): shutil.rmtree(staged)
        shutil.copytree(roots[0], staged)
        apply_pierre_local_only_patch(staged)
        if target.exists(): shutil.rmtree(target)
        staged.rename(target)
    marker.write_text(json.dumps({'lock': lock, 'patchSHA256': patch_sha256,
                                  'identity': _identity(target)}, sort_keys=True, indent=2)+'\n')


def apply_pierre_local_only_patch(root):
    patch_bridge = '''renderPatch(e){try{let t=typeof e=="string"?JSON.parse(e):e,{patch:n,fileName:a,options:r={}}=t;Z&&bp(),ee&&(ee.cleanUp(),ee=null);let i=fp();i.innerHTML="",r.theme&&(Rn=typeof r.theme=="string"?{dark:r.theme,light:r.theme}:{dark:r.theme.dark||"pierre-dark",light:r.theme.light||"pierre-light"},up=r.themeType==="light"?Rn.light:Rn.dark),r.diffStyle&&(Ap=r.diffStyle),r.overflow&&(mp=r.overflow);let o=Tp(n,{throwOnError:!0});o.lang||(o.lang=RB(a||o.name)),gp=null,gn=null;let c={theme:Rn,themeType:r.themeType||(up.includes("light")?"light":"dark"),diffStyle:Ap,diffIndicators:r.diffIndicators||"bars",hunkSeparators:r.hunkSeparators||"line-info",lineDiffType:r.lineDiffType||"word-alt",overflow:mp,enableLineSelection:r.enableLineSelection??!0,disableLineNumbers:r.disableLineNumbers??!1,disableFileHeader:r.disableFileHeader??!1,disableBackground:r.disableBackground??!1,expandUnchanged:!1,stickyHeader:r.stickyHeader??!1,renderAnnotation(s){return W6(s)},onLineClick:({lineNumber:s,side:l})=>me("lineClicked",{lineNumber:s,side:l,lineY:0,lineHeight:22}),onLineSelectionEnd:s=>{s&&me("selectionChanged",{startLine:s.start,endLine:s.end,side:s.side})}};r.maxLineDiffLength!=null&&(c.maxLineDiffLength=r.maxLineDiffLength),r.tokenizeMaxLength!=null&&(c.tokenizeMaxLength=r.tokenizeMaxLength),r.tokenizeMaxLineLength!=null&&(c.tokenizeMaxLineLength=r.tokenizeMaxLineLength),ee=new hi(c),ee.render({fileDiff:o,containerWrapper:i,lineAnnotations:[]}),me("ready")}catch(t){console.error("Error rendering patch:",t),me("error",{message:t.message})}},'''
    replacements = {
        'Sources/PierreDiffsSwift/WebView/PierreDiffView.swift': [
            ('    let configuration = WKWebViewConfiguration()\n',
             '    let configuration = WKWebViewConfiguration()\n    configuration.websiteDataStore = .nonPersistent()\n'),
            ('    configuration.preferences.setValue(true, forKey: "developerExtrasEnabled")\n',
             '    configuration.preferences.setValue(false, forKey: "developerExtrasEnabled")\n'),
            ('  let newContent: String\n',
             '  let newContent: String\n\n  /// Optional unified patch used for bounded previews of large files.\n  var patch: String?\n'),
            ('    self.newContent = newContent\n',
             '    self.newContent = newContent\n    self.patch = nil\n'),
            ('    self.onReady = onReady\n  }\n\n  // MARK: - NSViewRepresentable\n',
             '    self.onReady = onReady\n  }\n\n'
             '  public init(\n'
             '    patch: String,\n'
             '    fileName: String,\n'
             '    diffStyle: Binding<DiffStyle>,\n'
             '    overflowMode: Binding<OverflowMode>,\n'
             '    renderOptions: PierreDiffRenderOptions = PierreDiffRenderOptions(),\n'
             '    onReady: (() -> Void)? = nil\n'
             '  ) {\n'
             '    self.init(oldContent: "", newContent: "", fileName: fileName, diffStyle: diffStyle,\n'
             '              overflowMode: overflowMode, renderOptions: renderOptions, onReady: onReady)\n'
             '    self.patch = patch\n'
             '  }\n\n'
             '  // MARK: - NSViewRepresentable\n'),
            ('    if coordinator.lastEditedContent == newContent {\n',
             '    if patch == nil, coordinator.lastEditedContent == newContent {\n'),
            ('                         coordinator.lastFileName != fileName\n',
             '                         coordinator.lastFileName != fileName ||\n'
             '                         coordinator.lastPatch != patch\n'),
            ('      coordinator.lastOldContent = oldContent\n      coordinator.lastNewContent = newContent\n',
             '      coordinator.lastOldContent = oldContent\n      coordinator.lastNewContent = newContent\n'
             '      coordinator.lastPatch = patch\n'),
            ('      coordinator.renderDiff(\n'
             '        oldContent: oldContent,\n'
             '        newContent: newContent,\n'
             '        fileName: fileName,\n'
             '        theme: currentTheme,\n'
             '        diffStyle: diffStyle,\n'
             '        overflowMode: overflowMode,\n'
             '        renderOptions: renderOptions,\n'
             '        annotations: annotations\n'
             '      )\n',
             '      if let patch {\n'
             '        coordinator.renderPatch(patch: patch, fileName: fileName, theme: currentTheme,\n'
             '                                diffStyle: diffStyle, overflowMode: overflowMode,\n'
             '                                renderOptions: renderOptions)\n'
             '      } else {\n'
             '        coordinator.renderDiff(oldContent: oldContent, newContent: newContent, fileName: fileName,\n'
             '                               theme: currentTheme, diffStyle: diffStyle, overflowMode: overflowMode,\n'
             '                               renderOptions: renderOptions, annotations: annotations)\n'
             '      }\n'),
        ],
        'Sources/PierreDiffsSwift/WebView/DiffHTMLTemplate.swift': [
            ('        <meta charset="UTF-8">\n',
             '        <meta charset="UTF-8">\n        <meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'">\n'),
        ],
        'Sources/PierreDiffsSwift/WebView/DiffWebViewCoordinator.swift': [
            ('import WebKit\n',
             'import WebKit\n\nprivate struct PierrePatchInput: Encodable {\n'
             '  let patch: String\n  let fileName: String\n  let options: PierreDiffInput.Options\n}\n'),
            ('  var lastNewContent: String?\n',
             '  var lastNewContent: String?\n  var lastPatch: String?\n'),
            ('    setTheme(theme)\n  }\n\n  /// Sets the current theme\n',
             '    setTheme(theme)\n  }\n\n'
             '  /// Renders a bounded unified patch while preserving its original line numbers.\n'
             '  func renderPatch(patch: String, fileName: String, theme: String, diffStyle: DiffStyle,\n'
             '                   overflowMode: OverflowMode = .scroll,\n'
             '                   renderOptions: PierreDiffRenderOptions = PierreDiffRenderOptions()) {\n'
             '    let input = PierrePatchInput(patch: patch, fileName: fileName, options: PierreDiffInput.Options(\n'
             '      theme: PierreDiffInput.ThemeConfig(renderOptions.theme), themeType: theme,\n'
             '      diffStyle: diffStyle.rawValue, overflow: overflowMode.rawValue, enableLineSelection: true,\n'
             '      renderOptions: renderOptions))\n'
             '    executeWhenReady { [weak self] in self?.callJavaScript("renderPatch", with: input) }\n'
             '    setTheme(theme)\n'
             '  }\n\n'
             '  /// Sets the current theme\n'),
            ('extension DiffWebViewCoordinator: WKNavigationDelegate {\n\n',
             'extension DiffWebViewCoordinator: WKNavigationDelegate {\n\n'
             '  public func webView(\n'
             '    _ webView: WKWebView,\n'
             '    decidePolicyFor navigationAction: WKNavigationAction,\n'
             '    decisionHandler: @escaping (WKNavigationActionPolicy) -> Void\n'
             '  ) {\n'
             '    let scheme = navigationAction.request.url?.scheme\n'
             '    decisionHandler(scheme == nil || scheme == "about" ? .allow : .cancel)\n'
             '  }\n\n'),
        ],
        'Sources/PierreDiffsSwift/Resources/pierre-diffs-bundle.js': [
            ('window.pierreBridge={renderDiff(e){',
             'window.pierreBridge={' + patch_bridge + 'renderDiff(e){'),
            ('window.PierreDiffs={FileDiff:hi,parseDiffFromFile:je};',
             'window.PierreDiffs={FileDiff:hi,parseDiffFromFile:je,parsePatchFile:Tp};'),
        ],
    }
    for relative, changes in replacements.items():
        path = root/relative
        text = path.read_text()
        for before, after in changes:
            if text.count(before) != 1:
                raise ValueError(f'PierreDiffsSwift patch context changed: {relative}: {before[:80]!r}')
            text = text.replace(before, after)
        path.write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--archive', type=Path)
    args = parser.parse_args(); print(prepare(args.archive))
