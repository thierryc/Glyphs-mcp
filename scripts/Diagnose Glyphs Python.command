#!/bin/zsh
# Double-click in Finder, or run with zsh. No installs, preference changes,
# font edits, or Glyphs launches. Output is printed directly in Terminal.
emulate -LR zsh
setopt PIPE_FAIL
exec 2>&1

section() { print; print -r -- "=== $1 ==="; }

probe_python() {
    local executable="$1"
    print -r -- "" "Candidate: $executable"
    /bin/ls -ld "$executable" 2>/dev/null
    if [[ ! -x "$executable" ]]; then
        print -r -- "Missing or not executable."
        return
    fi
    # Run without user site packages or bytecode writes; cap startup at 15s.
    PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 /usr/bin/perl -e '
        alarm 15; exec @ARGV; die "Cannot execute interpreter: $!\n";
    ' "$executable" -I -B -c '
import json, os, platform, sys, sysconfig
print(json.dumps({
    "version": sys.version,
    "executable": sys.executable,
    "resolvedExecutable": os.path.realpath(sys.executable),
    "prefix": sys.prefix,
    "basePrefix": getattr(sys, "base_prefix", sys.prefix),
    "architecture": platform.machine(),
    "SOABI": sysconfig.get_config_var("SOABI"),
}, indent=2))
' </dev/null
    local probe_exit=$?
    (( probe_exit == 0 )) || print -r -- "Probe failed or timed out (exit $probe_exit)."
}

print -r -- "Glyphs Python diagnostic"
/bin/date -u '+UTC: %Y-%m-%d %H:%M:%S'
/usr/bin/sw_vers
print -r -- "Shell architecture: $(/usr/bin/uname -m)"
print -r -- "Configured framework, external Python, MCP sidecar, and loaded Glyphs Python are separate evidence."

section "Running Glyphs processes and loaded Python libraries"
found=0
process_list=$(/bin/ps -axo pid=,comm= 2>/dev/null)
process_exit=$?
while read -r pid executable; do
    # ps supplies PID and executable path only, without command arguments.
    if [[ "$executable" != *Glyphs*.app/Contents/MacOS/* ]]; then
        continue
    fi
    found=1
    print -r -- "PID $pid: $executable"
    if [[ -x /usr/sbin/lsof ]]; then
        loaded=$(/usr/sbin/lsof -n -P -p "$pid" -Fn 2>/dev/null | /usr/bin/awk '
            /^n/ && /Python\.framework|libpython|Python\.plugin|GlyphsPythonPlugin/ {print substr($0,2)}
        ' | /usr/bin/sort -u)
        if [[ -n "$loaded" ]]; then
            print -r -- "$loaded"
        else
            print -r -- "No Python libraries visible to lsof; this does not establish that Python is absent."
        fi
    fi
done <<< "$process_list"
if (( process_exit != 0 )); then
    print -r -- "Process inspection unavailable in this execution environment. Run from Terminal to check loaded libraries."
elif (( ! found )); then
    print -r -- "No running Glyphs application found."
fi

section "Glyphs Python settings (stable and beta domains)"
typeset -A seen
for domain in com.GeorgSeifert.Glyphs3 com.GeorgSeifert.Glyphs3Beta com.GeorgSeifert.Glyphs4 com.GeorgSeifert.Glyphs4Beta com.GeorgSeifert.GlyphsBeta; do
    framework=$(/usr/bin/defaults read "$domain" GSPythonFrameworkPath 2>/dev/null)
    if [[ -z "$framework" ]]; then
        print -r -- "$domain: no explicit GSPythonFrameworkPath"
        continue
    fi
    print -r -- "$domain: $framework"
    candidate="$framework/bin/python3"
    if [[ -z "${seen[$candidate]}" ]]; then
        seen[$candidate]=1
        probe_python "$candidate"
    fi
done

section "Installed Glyphs application paths"
/usr/bin/mdfind 'kMDItemCFBundleIdentifier == "com.GeorgSeifert.Glyphs*"' 2>/dev/null
print -r -- "Spotlight results may omit unindexed apps; compare with the running process path above."

section "Glyphs Python plugin and system framework candidates"
for root in "$HOME/Library/Application Support/Glyphs 3/Repositories/GlyphsPythonPlugin/Python.framework" \
            "$HOME/Library/Application Support/Glyphs 4/Repositories/GlyphsPythonPlugin/Python.framework" \
            /Library/Frameworks/Python.framework "$HOME/Library/Frameworks/Python.framework"; do
    [[ -d "$root" ]] || continue
    for candidate in "$root"/Versions/*/bin/python3(N); do
        [[ -z "${seen[$candidate]}" ]] || continue
        seen[$candidate]=1
        probe_python "$candidate"
    done
done

section "MCP installed runtime identity (separate from Glyphs Python)"
mcp_root="$HOME/Library/Application Support/Glyphs MCP/lean-v2"
for receipt in "$mcp_root/installation.json" "$mcp_root/installation.dev.json"; do
    [[ -f "$receipt" ]] || continue
    print -r -- "Receipt: $receipt"
    /bin/ls -ld "$receipt"
    # Print only runtime-related fields, not the entire receipt.
    for key in python pythonVersion glyphsApp buildRoot; do
        value=$(/usr/bin/plutil -extract "$key" raw -o - "$receipt" 2>/dev/null)
        [[ -n "$value" ]] && print -r -- "$key: $value"
        if [[ "$key" == python && "$value" == /* && -z "${seen[$value]}" ]]; then
            seen[$value]=1
            probe_python "$value"
        fi
    done
done
for candidate in "$mcp_root"/runtimes/*/bin/python3(N); do
    probe_python "$candidate"
done

section "Authoritative check inside the open Glyphs app"
/bin/cat <<'MACRO'
Run the following in Glyphs' Macro Panel and compare its output with this report.
This reports the interpreter already loaded in the app. External probes above
cannot establish that exact interpreter version.

import json, platform, sys, sysconfig
print(json.dumps({
    "version": sys.version,
    "executable": sys.executable,
    "prefix": sys.prefix,
    "basePrefix": getattr(sys, "base_prefix", sys.prefix),
    "architecture": platform.machine(),
    "SOABI": sysconfig.get_config_var("SOABI"),
}, indent=2))

A framework setting that differs from the loaded library or Macro Panel output
can indicate a pending restart, a different app copy, or stale preferences.
The MCP sidecar can legitimately use a different Python version.
MACRO
print
print -r -- "Diagnostic complete."
if [[ -t 0 && "${1:-}" != "--no-pause" ]]; then
    read -r '?Press Return to close this window.'
fi
