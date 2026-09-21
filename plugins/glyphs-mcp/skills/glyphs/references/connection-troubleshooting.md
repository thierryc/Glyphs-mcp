# Connection troubleshooting

Record the **configured endpoint and connection identifier** before diagnosing.
The unchanged v2 default is `http://127.0.0.1:9680/mcp/`; its authenticated internal
bridge defaults to loopback port 9681. Read the actual endpoint from the client
configuration or Glyphs MCP’s Setup page; do not assume a default is configured.
In Glyphs 4, open **Edit → Glyphs MCP Server…** for server status and controls.
In the Glyphs MCP desktop app, use Setup and **Open Troubleshooting Logs** for
worker and installation evidence. Never expose the bridge token in a report.

| Evidence | Explanation and recovery |
|---|---|
| Nine-tool catalog, skill demands other tools | Wrong skill. Select the shipped lean `$glyphs`; inspect the conflicting skill path. Re-run skill setup to refresh an unchanged installer-owned skill. For preserved conflicts, use **Replace preserved skills (backup)** in the installer; review the preserved path first. Plugin caches are managed by their plugin, never edited in place. |
| Required private lean capability/job or current interface metadata missing | The installation needs updating. Update the bridge, sidecar and skills together through the installer, reload affected processes, and verify the negotiated capabilities. Do not substitute workflows from earlier private v2 builds. |
| v1 identity with v2 instructions | Wrong skill for this connection. Use the separate v1.11.0 distribution and its skills, or configure the intended v2 connection explicitly. The lean v2 payload contains no `skills-v1`. A successful v1 handshake does not indicate a stopped server. |
| Sidecar responds, `bridge.reachable: false` | Check whether the intended Glyphs 4 process is still running. If it unexpectedly exited, use [crash recovery](crash-recovery.md) before reopening it. Otherwise inspect Edit → Glyphs MCP Server…. Check bridge installation, endpoint and panel error; start it explicitly when authorized. Do not reinstall skills to fix a stopped bridge. |
| `worker.available: false` | Inspect `worker.executable`, application path and setup/preflight error. Repair the worker/runtime component through the installer; reads may remain available. |
| Address already in use or unexpected catalog | Identify the process holding the configured port. Stop the unintended server when authorized, or explicitly configure a separate free loopback port for v1. Never switch v2’s port automatically. |
| Receipt expects different sidecar/bridge fingerprint | Name the differing component. Files may have been updated while an older process remains loaded. Once current jobs are settled, explicitly stop/start the sidecar for a stale sidecar; reopen Glyphs to reload a stale bridge, resolving unsaved documents with the user first. Never claim that restarting the sidecar reloads the bridge. |
| Hash missing or unreadable | Report identity unavailable, never “matches.” Repair or update the current private installation and verify fresh identity before claiming a verified installation. |
| `get_job` reports `interrupted` / `bridge_operation_lost` | The acknowledged native operation is no longer available after a restart or expiry of retained history. Final edits/restoration are unverified; the retained progress is only the last observation. Keep this job ID and report. Do not replay its patch or claim discard succeeded. Inspect the intended font; obtain a fresh document ID after restart and prepare new work only when requested. |
| Font dirty or unsaved | Connection identification and bounded live reads still work. Saved-source jobs require a saved, clean source; use authorized Save/Save As or a disposable copy. Do not save merely to identify the interface. |

For coexistence, keep separate named connections and free loopback ports. Glyphs
3.5 and Glyphs 4 can share the display name “Glyphs”; identify them by bundle ID:
`com.GeorgSeifert.Glyphs3` and `com.GeorgSeifert.Glyphs4`. v1’s port is configurable;
record and restore temporary changes. No automatic port switching or restarts.

After a missing-operation error from apply/discard, poll the same job with
`get_job(include_preview=false)` to reconcile its state. Timeouts, stopped bridges
and requests without native acknowledgement remain uncertain: restore the
connection and inspect the same job; do not resubmit or force an installer stop.
An interrupted job is retained evidence, not an active write or restored font.
