#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_svg="$repo_root/macos-installer/DMG/background.svg"
output_png="$repo_root/macos-installer/DMG/background.png"
tmp_root="$(mktemp -d "/tmp/gmcp-dmg-background.XXXXXX")"

cleanup() { rm -rf "$tmp_root"; }
trap cleanup EXIT

# Quick Look uses the system text renderer, which keeps the installer copy
# faithful to the macOS fonts used by Finder. Its square thumbnail is cropped
# back to the SVG's exact 680x420 canvas afterward.
/usr/bin/qlmanage -t -s 680 -o "$tmp_root" "$source_svg" >/dev/null
rendered="$tmp_root/$(basename "$source_svg").png"

if [[ ! -f "$rendered" ]]; then
  echo "error: Quick Look did not render $source_svg" >&2
  exit 1
fi

if ! command -v magick >/dev/null 2>&1; then
  echo "error: ImageMagick is required to crop the Quick Look preview" >&2
  exit 1
fi

magick "$rendered" -crop 680x420+0+0 +repage "$output_png"
echo "Rendered: $output_png (680x420)"
