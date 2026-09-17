#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_svg="$repo_root/macos-installer/DMG/background.svg"
output_png="$repo_root/macos-installer/DMG/background.png"
output_retina_png="$repo_root/macos-installer/DMG/background@2x.png"
output_tiff="$repo_root/macos-installer/DMG/background.tiff"
tmp_root="$(mktemp -d "/tmp/gmcp-dmg-background.XXXXXX")"

cleanup() { rm -rf "$tmp_root"; }
trap cleanup EXIT

if ! command -v magick >/dev/null 2>&1; then
  echo "error: ImageMagick is required to crop the Quick Look preview" >&2
  exit 1
fi

# Quick Look uses the system text renderer, which keeps the installer copy
# faithful to the macOS fonts used by Finder. Render both native point and
# Retina pixel sizes, then combine them into the multi-representation TIFF that
# Finder uses as the disk-image background.
render_representation() {
  local scale="$1"
  local width=$((680 * scale))
  local height=$((420 * scale))
  local render_dir="$tmp_root/${scale}x"
  local rendered="$render_dir/$(basename "$source_svg").png"
  local destination="$output_png"

  if [[ "$scale" == "2" ]]; then destination="$output_retina_png"; fi
  mkdir -p "$render_dir"
  /usr/bin/qlmanage -t -s "$width" -o "$render_dir" "$source_svg" >/dev/null
  if [[ ! -f "$rendered" ]]; then
    echo "error: Quick Look did not render $source_svg at ${scale}x" >&2
    exit 1
  fi
  magick "$rendered" -crop "${width}x${height}+0+0" +repage "$destination"
}

render_representation 1
render_representation 2
/usr/bin/tiffutil -cathidpicheck "$output_png" "$output_retina_png" -out "$output_tiff" >/dev/null

echo "Rendered: $output_tiff (680x420 points, 1x and 2x representations)"
