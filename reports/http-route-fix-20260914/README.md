# Installed HTTP route correction

The configured `/mcp/` endpoint is now served directly using FastMCP's existing
path option. Seven tools and their schemas remain unchanged. The installed
sidecar is `2.0.0-beta.1+82daa62ac227`; bridge, companions and skills are unchanged.

581 lean tests pass. The live comparison records 12 tool calls / 24 HTTP exchanges
before, versus 12 / 12 after, with identical read/error evidence. Timing is not a
matched-load performance comparison. The first installation was refused by the
existing Glyphs-closed guard; a normal close/install/relaunch restored the clean
disposable font. No Undo, queue-tail or autosave fix is included.

The archive contains the full follow-up folder, logs, scripts, first refused
installation, completed receipt, frozen identities and verification, plus the
historical P07 report/proposal and updated coverage index. Every archive member
was read back and checksum verified. Extract into a fresh directory:

```sh
mkdir route-evidence
tar -xzf evidence.tar.gz -C route-evidence
```

Then open `route-evidence/reports/v1-v2/07-stored-kerning/http-route-fix-20260914/report.md`.
The older P07 report's full raw evidence remains in its original worktree folder;
it is not duplicated here. Qualification scripts contain historical paths and
phase folders that deliberately refuse overwriting the recorded run. Read the
specification and use new output paths before any authorized replay.

No private font source or credential is included. No release was published.
