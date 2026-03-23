#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Build and upload Glyphs MCP release assets to an existing GitHub release.

Usage:
  ./scripts/publish_release_assets.sh [--tag vX.Y.Z] [--skip-build] [--include-plugin-zip]

Options:
  --tag vX.Y.Z          Release tag to upload to (default: v<CFBundleShortVersionString>)
  --skip-build          Upload existing artifacts from dist/ without rebuilding
  --include-plugin-zip  Also build/upload dist/Glyphs MCP.glyphsPlugin-v<VERSION>.zip
  -h, --help            Show this help
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

info_plist="$repo_root/src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Info.plist"
version=""
tag=""
skip_build="0"
include_plugin_zip="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      tag="${2:-}"
      shift 2
      ;;
    --skip-build)
      skip_build="1"
      shift
      ;;
    --include-plugin-zip)
      include_plugin_zip="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -x /usr/libexec/PlistBuddy ]]; then
  version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$info_plist" 2>/dev/null || true)"
fi
if [[ -z "$version" ]]; then
  echo "error: could not determine version from $info_plist" >&2
  exit 1
fi

if [[ -z "$tag" ]]; then
  tag="v$version"
fi

if [[ "$skip_build" != "1" ]]; then
  ./scripts/build_installer_app.sh
  ./scripts/notarize_installer_app.sh
  ./scripts/make_installer_dmg.sh
  if [[ "$include_plugin_zip" == "1" ]]; then
    ./scripts/build_release_zip.sh --version "$version"
  fi
fi

assets=(
  "$repo_root/dist/GlyphsMCPInstaller-$version.dmg"
  "$repo_root/dist/GlyphsMCPInstaller.dmg"
  "$repo_root/dist/installer-app/GlyphsMCPInstaller.zip"
)

if [[ "$include_plugin_zip" == "1" ]]; then
  assets+=("$repo_root/dist/Glyphs MCP.glyphsPlugin-v$version.zip")
fi

for asset in "${assets[@]}"; do
  if [[ ! -f "$asset" ]]; then
    echo "error: missing asset: $asset" >&2
    exit 1
  fi
done

echo "Uploading assets to release $tag:"
for asset in "${assets[@]}"; do
  echo "  - $asset"
done

gh release upload "$tag" "${assets[@]}" --clobber
echo "Done."
