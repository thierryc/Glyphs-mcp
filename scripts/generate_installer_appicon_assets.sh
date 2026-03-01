#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

src_svg="$repo_root/macos-installer/GlyphsMCPInstaller/Resources/macos-installer.icon/Assets/main.svg"
out_dir="$repo_root/macos-installer/GlyphsMCPInstaller/Resources/Assets.xcassets/AppIcon.appiconset"
tmp_dir="/tmp/gmcp-installer-appicon"

if [[ ! -f "$src_svg" ]]; then
  echo "error: missing SVG: $src_svg" >&2
  exit 1
fi

mkdir -p "$out_dir"
rm -rf "$tmp_dir"
mkdir -p "$tmp_dir"

echo "Rendering SVG → 1024 PNG…"
base_png="$tmp_dir/base-1024.png"

if command -v rsvg-convert >/dev/null 2>&1; then
  # brew install librsvg
  rsvg-convert -w 1024 -h 1024 "$src_svg" -o "$base_png"
elif command -v inkscape >/dev/null 2>&1; then
  inkscape "$src_svg" --export-type=png --export-width=1024 --export-height=1024 --export-filename="$base_png" >/dev/null 2>&1
else
  echo "error: can't render SVG on this machine." >&2
  echo "Install one of:" >&2
  echo "  - librsvg (recommended): brew install librsvg" >&2
  echo "  - Inkscape: https://inkscape.org" >&2
  exit 1
fi

echo "Writing icons into: $out_dir"
cp "$base_png" "$out_dir/icon_512x512@2x.png"

resize() {
  local size="$1"
  local out="$2"
  /usr/bin/sips -Z "$size" "$base_png" --out "$out" >/dev/null
}

resize 512 "$out_dir/icon_512x512.png"
resize 256 "$out_dir/icon_256x256.png"
resize 512 "$out_dir/icon_256x256@2x.png"
resize 128 "$out_dir/icon_128x128.png"
resize 256 "$out_dir/icon_128x128@2x.png"
resize  32 "$out_dir/icon_32x32.png"
resize  64 "$out_dir/icon_32x32@2x.png"
resize  16 "$out_dir/icon_16x16.png"
resize  32 "$out_dir/icon_16x16@2x.png"

echo "Done. Re-open Xcode (or build once) to refresh the AppIcon preview."
