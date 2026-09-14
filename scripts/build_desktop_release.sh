#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
"$python_bin" "$repo_root/scripts/prepare_desktop_dependencies.py"
bash "$repo_root/scripts/build_installer_app.sh"
bash "$repo_root/scripts/notarize_installer_app.sh"
bash "$repo_root/scripts/make_installer_dmg.sh"
"$python_bin" "$repo_root/scripts/prepare_desktop_update.py" \
  --app "$repo_root/dist/installer-app/Glyphs MCP.app" \
  --output "$repo_root/dist/desktop-update"
echo "Signed local desktop candidate prepared. Nothing has been published."
