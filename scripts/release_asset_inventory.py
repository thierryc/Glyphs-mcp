"""Shared desktop release upload and checksum inventory for both channels."""
import argparse
from pathlib import Path
from desktop_release_identity import load


def assets(root, release, product='Glyphs MCP', *, include_manifest=False):
    root = Path(root)
    version = release['releaseVersion']
    paths = [root/f'dist/Glyphs-MCP-{version}.dmg',
             root/f'dist/desktop-update/Glyphs-MCP-{version}.zip',
             root/'dist/desktop-update/appcast.xml']
    if release['channel'] == 'stable':
        paths.extend([root/'dist/Glyphs-MCP-latest.dmg', root/f'dist/installer-app/{product}.zip'])
    if include_manifest:
        paths.append(root/'dist/SHA256SUMS')
    return paths


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--product', default='Glyphs MCP')
    parser.add_argument('--include-manifest', action='store_true')
    args = parser.parse_args()
    print('\n'.join(str(path) for path in assets(args.repo_root, load(args.repo_root), args.product,
                                               include_manifest=args.include_manifest)))
