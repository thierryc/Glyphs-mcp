#!/usr/bin/env python3
"""Register new desktop Swift files in the existing Xcode targets deterministically."""
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / 'macos-installer/GlyphsMCPInstaller'
PROJECT = ROOT / 'GlyphsMCPInstaller.xcodeproj/project.pbxproj'
GROUPS = {
    'Sources': ('AA0000000000000000000003', 'AA0000000000000000000011'),
    'Core': ('AA00000000000000000000C7', 'AA00000000000000000000C5'),
    'Tests/GlyphsMCPInstallerTests': ('AA0000000000000000000008', 'AA0000000000000000000017'),
}


def sync():
    text = PROJECT.read_text()
    for folder, (group, phase) in GROUPS.items():
        for path in sorted((ROOT / folder).glob('*.swift')):
            # This historical, uncompiled file duplicates Preflight definitions.
            if path.name == 'AdvancedMode.swift':
                continue
            if re.search(r'path = "?' + re.escape(path.name) + r'"?;', text):
                continue
            identity = str(path.relative_to(ROOT))
            ref = hashlib.sha256(('file:' + identity).encode()).hexdigest()[:24].upper()
            build = hashlib.sha256(('build:' + identity).encode()).hexdigest()[:24].upper()
            file_line = f'\t\t{ref} /* {path.name} */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = "{path.name}"; sourceTree = "<group>"; }};\n'
            build_line = f'\t\t{build} /* {path.name} in Sources */ = {{isa = PBXBuildFile; fileRef = {ref} /* {path.name} */; }};\n'
            text = text.replace('/* End PBXFileReference section */', file_line + '/* End PBXFileReference section */')
            text = text.replace('/* End PBXBuildFile section */', build_line + '/* End PBXBuildFile section */')
            for target, key, line in ((group, 'children', f'{ref} /* {path.name} */'),
                                      (phase, 'files', f'{build} /* {path.name} in Sources */')):
                pattern = r'(\t\t' + target + r'[^\n]*= \{[\s\S]*?\b' + key + r' = \(\n)'
                text, count = re.subn(pattern, lambda m: m[1] + '\t\t\t\t' + line + ',\n', text, count=1)
                assert count == 1, target
    PROJECT.write_text(text)


if __name__ == '__main__':
    sync()
