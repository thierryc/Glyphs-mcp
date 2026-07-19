#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Build and upload Glyphs MCP release assets to an existing GitHub release.

Usage:
  ./scripts/publish_release_assets.sh --tag vX.Y.Z [--skip-build] [--include-plugin-zip]
      [--dry-run] [--confirm-publish vX.Y.Z] [--allow-unsigned-tag]

Options:
  --tag vX.Y.Z          Exact signed release tag. Must match all source and app versions.
  --skip-build          Reuse existing artifacts, but still run every verification gate.
  --include-plugin-zip  Also build/upload dist/Glyphs MCP.glyphsPlugin-v<VERSION>.zip
  --dry-run             Build and verify locally without uploading anything.
  --confirm-publish TAG Non-interactive confirmation; value must exactly equal --tag.
  --allow-unsigned-tag  Explicitly allow an annotated but unsigned tag (not recommended).
  -h, --help            Show this help
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

version=""
tag=""
skip_build="0"
include_plugin_zip="0"
dry_run="0"
confirm_publish=""
allow_unsigned_tag="0"

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
    --dry-run)
      dry_run="1"
      shift
      ;;
    --confirm-publish)
      confirm_publish="${2:-}"
      shift 2
      ;;
    --allow-unsigned-tag)
      allow_unsigned_tag="1"
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

if [[ -z "$tag" ]]; then
  echo "error: --tag vX.Y.Z is required for a release publish" >&2
  exit 2
fi

if [[ "${SKIP_NOTARIZATION:-0}" == "1" ]]; then
  echo "error: publishing is disabled when SKIP_NOTARIZATION=1" >&2
  exit 1
fi

version="$(python3 "$repo_root/scripts/release_security.py" metadata --repo-root "$repo_root" --tag "$tag")"

expected_branch="${EXPECTED_RELEASE_BRANCH:-main}"
branch="$(git branch --show-current)"
if [[ "$branch" != "$expected_branch" ]]; then
  echo "error: releases must be published from '$expected_branch' (current: '$branch')" >&2
  exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "error: release worktree/index is not clean" >&2
  exit 1
fi

if [[ "$(git cat-file -t "refs/tags/$tag" 2>/dev/null || true)" != "tag" ]]; then
  echo "error: $tag must exist locally as an annotated tag" >&2
  exit 1
fi
tag_commit="$(git rev-parse "$tag^{commit}")"
head_commit="$(git rev-parse HEAD)"
if [[ "$tag_commit" != "$head_commit" ]]; then
  echo "error: $tag points to $tag_commit, not current HEAD $head_commit" >&2
  exit 1
fi

if [[ "$allow_unsigned_tag" != "1" ]]; then
  if ! git verify-tag "$tag" >/dev/null 2>&1; then
    echo "error: $tag does not have a valid local signature" >&2
    echo "Use a signed tag, or explicitly pass --allow-unsigned-tag after reviewing the commit." >&2
    exit 1
  fi
fi

if ! git fetch --quiet origin "$expected_branch"; then
  echo "error: could not fetch origin/$expected_branch for release verification" >&2
  exit 1
fi
remote_branch_commit="$(git rev-parse FETCH_HEAD)"
if [[ "$remote_branch_commit" != "$head_commit" ]]; then
  echo "error: local HEAD does not match origin/$expected_branch" >&2
  echo "Push and review the exact release commit before publishing." >&2
  exit 1
fi

remote_tag_commit="$(git ls-remote origin "refs/tags/$tag^{}" | awk 'NR == 1 { print $1 }')"
if [[ -z "$remote_tag_commit" || "$remote_tag_commit" != "$head_commit" ]]; then
  echo "error: remote annotated tag $tag is missing or does not point to release HEAD" >&2
  exit 1
fi

./scripts/run_local_release_tests.sh

if [[ "$skip_build" != "1" ]]; then
  ./scripts/build_installer_app.sh
  ./scripts/notarize_installer_app.sh
  ./scripts/make_installer_dmg.sh
  if [[ "$include_plugin_zip" == "1" ]]; then
    ./scripts/build_release_zip.sh --version "$version"
  fi
fi

verify_args=(--tag "$tag" --write-checksums)
if [[ "$include_plugin_zip" == "1" ]]; then
  verify_args+=(--include-plugin-zip)
fi
./scripts/verify_release_artifacts.sh "${verify_args[@]}"

assets=(
  "$repo_root/dist/GlyphsMCPInstaller-$version.dmg"
  "$repo_root/dist/GlyphsMCPInstaller.dmg"
  "$repo_root/dist/installer-app/GlyphsMCPInstaller.zip"
  "$repo_root/dist/SHA256SUMS"
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

if [[ "$dry_run" == "1" ]]; then
  echo "Dry run complete. Artifacts passed local release verification; nothing was uploaded."
  exit 0
fi

if [[ -t 0 ]]; then
  echo "About to upload verified artifacts for $tag."
  read -r -p "Type the exact tag to continue: " typed_tag
  if [[ "$typed_tag" != "$tag" ]]; then
    echo "Publish cancelled; confirmation did not match $tag." >&2
    exit 1
  fi
elif [[ "$confirm_publish" != "$tag" ]]; then
  echo "error: non-interactive publishing requires --confirm-publish $tag" >&2
  exit 1
fi

if ! release_json="$(gh release view "$tag" --json tagName,isDraft,assets 2>/dev/null)"; then
  echo "error: GitHub release $tag does not exist or is not accessible" >&2
  exit 1
fi

asset_names=()
for asset in "${assets[@]}"; do
  asset_names+=("$(basename "$asset")")
done
release_state_args=(release-state --tag "$tag" --release-json "$release_json")
for asset_name in "${asset_names[@]}"; do
  release_state_args+=(--expect-name "$asset_name")
done
if ! python3 "$repo_root/scripts/release_security.py" "${release_state_args[@]}" >/dev/null; then
  exit 1
fi

echo "Uploading assets to release $tag:"
for asset in "${assets[@]}"; do
  echo "  - $asset"
done

gh release upload "$tag" "${assets[@]}"
echo "Done."
