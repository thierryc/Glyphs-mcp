#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$repo_root/macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj"
scheme="GlyphsMCPInstaller"
started_at="$SECONDS"
python_bin="${PYTHON_BIN:-python3}"
xcodebuild_bin="${XCODEBUILD_BIN:-xcodebuild}"

# Xcode runs shell phases from the project directory, not the repository root.
# Resolve an explicitly relative interpreter before exporting it so the Copy
# Payload phase uses the same qualified Python as this release gate.
if [[ "$python_bin" == */* ]]; then
  if [[ "$python_bin" != /* ]]; then python_bin="$repo_root/$python_bin"; fi
elif ! python_bin="$(command -v "$python_bin")"; then
  echo "error: Python interpreter not found: ${PYTHON_BIN:-python3}" >&2
  exit 1
fi
if [[ ! -x "$python_bin" ]]; then
  echo "error: Python interpreter is not executable: $python_bin" >&2
  exit 1
fi
export PYTHON_BIN="$python_bin"

parallel=1
case "${1:-}" in
  --serial) parallel=0 ;;
  --help) echo "Usage: $0 [--serial]"; exit 0 ;;
  "") ;;
  *) echo "error: unknown option: $1" >&2; exit 2 ;;
esac
if [[ "$#" -gt 1 ]]; then echo "error: too many arguments" >&2; exit 2; fi

cd "$repo_root"
# Shared dependencies are prepared before concurrent readers start. Each run has
# isolated payload/build outputs and logs; never run two gates in one checkout.
mkdir -p "$repo_root/build"
lock_root="$repo_root/build/release-tests.lock"
if ! mkdir "$lock_root" 2>/dev/null; then
  echo "error: another release gate owns $lock_root; check its PID before removing a stale lock" >&2
  exit 1
fi
printf '%s\n' "$$" > "$lock_root/pid"
run_root="$(mktemp -d "$repo_root/build/release-test-run.XXXXXX")"
echo "Release test logs: $run_root"
payload_a="$run_root/payload-a"
payload_b="$run_root/payload-b"
derived_data="$run_root/DerivedData"
pids=()
# Bash job control gives each background lane its own process group, so an
# interrupted run terminates its compiler/test children as well as the wrapper.
set -m
cleanup() {
  for pid in "${pids[@]:-}"; do
    if [[ -n "$pid" ]]; then kill -TERM -- "-$pid" 2>/dev/null || true; fi
  done
  if [[ "${#pids[@]}" == 0 ]]; then rm -rf "$derived_data" "$payload_a" "$payload_b"; fi
  rm -f "$lock_root/pid"
  rmdir "$lock_root"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"$python_bin" scripts/prepare_desktop_dependencies.py
source_before="$("$python_bin" scripts/release_test_inputs.py)"

echo "Checking release scripts…"
for release_script in \
  scripts/build_installer_app.sh \
  scripts/build_desktop_release.sh \
  scripts/notarize_installer_app.sh \
  scripts/make_installer_dmg.sh \
  scripts/render_dmg_background.sh \
  scripts/publish_release_assets.sh \
  scripts/run_python_tests.sh \
  scripts/run_local_release_tests.sh \
  scripts/verify_release_artifacts.sh; do
  /bin/bash -n "$release_script"
done

echo "Checking tracked patch whitespace…"
git diff --check HEAD

echo "Checking the lean package and shipped skills…"
release_version="$("$python_bin" scripts/desktop_release_identity.py --field version)"
installer_build="$("$python_bin" scripts/desktop_release_identity.py --field installerBuild)"
beta_number="$("$python_bin" scripts/desktop_release_identity.py --field betaNumber)"
"$python_bin" scripts/bump_version.py --dry-run --beta "$beta_number" "$release_version"
scripts/sync_codex_plugin_skills.sh --check
"$python_bin" scripts/check_lean_package.py
"$python_bin" scripts/build_installer_payload.py --output-root "$payload_a"
"$python_bin" scripts/build_installer_payload.py --output-root "$payload_b"
diff -qr "$payload_a" "$payload_b"
"$python_bin" scripts/qualify_private_runtime.py "$payload_a/Lean"
# These lanes read the same frozen source, but write separate outputs. The
# Python suite stays serial internally: its shared-service fixtures are not
# automatically safe for pytest worker sharding.
python_checks() {
  GLYPHS_MCP_FULL_PYTHON_MATRIX=1 PYTHON_BIN="$python_bin" scripts/run_python_tests.sh --pytest
}
documentation_checks() { (cd website && npm run build); }
desktop_checks() {
  "$xcodebuild_bin" test \
    -project "$project" \
    -scheme "$scheme" \
    -configuration Debug \
    -destination 'platform=macOS' \
    -derivedDataPath "$derived_data" \
    -jobs "${GMCP_XCODE_JOBS:-4}" \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO || return $?
  # The scheme builds the app for testing. Verify those exact bytes, rather than
  # invoking build again and rerunning the unconditional Copy Payload phase.
  "$python_bin" scripts/verify_desktop_app.py "$derived_data/Build/Products/Debug/Glyphs MCP.app"
}
run_lane() {
  local name="$1" operation="$2" started="$SECONDS" result=0
  echo "Starting $name checks ($run_root/$name.log)…"
  (set -e; "$operation") > "$run_root/$name.log" 2>&1 || result=$?
  echo "$result" > "$run_root/$name.exit"
  echo "$((SECONDS - started))" > "$run_root/$name.seconds"
  if [[ "$result" -ne 0 ]]; then tail -n 40 "$run_root/$name.log" >&2; fi
  return "$result"
}
if [[ "$parallel" == 1 ]]; then
  run_lane python python_checks & pids+=("$!")
  run_lane desktop desktop_checks & pids+=("$!")
  run_lane documentation documentation_checks & pids+=("$!")
  result=0
  for pid in "${pids[@]}"; do wait "$pid" || result=1; done
  pids=()
  if [[ "$result" -ne 0 ]]; then echo "Release checks failed; see $run_root" >&2; exit 1; fi
else
  run_lane python python_checks
  run_lane desktop desktop_checks
  run_lane documentation documentation_checks
fi
for lane in python desktop documentation; do
  echo "$lane passed in $(cat "$run_root/$lane.seconds") seconds."
done

"$python_bin" scripts/release_security.py candidate --repo-root "$repo_root" --version "$release_version" --installer-build "$installer_build" --app-plist "$derived_data/Build/Products/Debug/Glyphs MCP.app/Contents/Info.plist" --payload-root "$payload_a" | tee "$run_root/candidate.json"

source_after="$("$python_bin" scripts/release_test_inputs.py)"
if [[ "$source_before" != "$source_after" ]]; then
  echo "error: release inputs changed during checks; rerun against stable source" >&2
  exit 1
fi
printf '%s\n' "$source_after" > "$run_root/inputs.sha256"
echo "Local release tests passed in $((SECONDS - started_at)) seconds. No artifacts were published."
