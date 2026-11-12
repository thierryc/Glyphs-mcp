# Skill update desktop verification — 2026-11-12

Implementation commit: `8729c774` (`fix: surface bundled skill updates and clarify reminders`).
The local build also included existing unrelated worktree changes; this report does not qualify a clean release build.

## Build and installation

- Built from current worktree using `python3 -B scripts/build_local_app.py`.
- Verified candidate against `dist/local/build-receipt.json` immediately before installation.
- Installed `/Applications/Glyphs MCP.app`, version 2.7.0, build 91.
- Installed bundle SHA-256: `092c874a4c7a2fceb4a408b76103c1b9be686d8cdbc65e4cf16c2421e541e07f`.
- Previous app retained locally under `dist/local/previous-companion-wtp6y3_b/Glyphs MCP.app`.
- Confirmed running process `/Applications/Glyphs MCP.app/Contents/MacOS/Glyphs MCP`.
- Existing runtime receipt remains version 2.7.1/build 92. No runtime installation or Glyphs restart was performed.

## Native UI observations

- Skills badge and separate banner report three distinct skills with updates.
- Review Skill Updates selects Show: Updates and shows Font Workflows, MCP Release, and Small and Petite Caps.
- Small and Petite Caps shows the new create/continue/refine/audit description.
- Its Claude Code copy shows Update available. The existing Codex copy remains Version unverified with explicit Replace; Cursor remains managed through AI Agents.
- After desktop relaunch, the badge appears while the project dashboard is visible, before opening Skills or selecting a skill.
- Refreshing Setup and relaunching produced no component update reminder. Skill notifications remain independent of component notifications.

## Popup verification limit

There is no eligible component update in the current installation: the installed MCP runtime is newer than the desktop payload; other component checks do not offer a verified update. The native popup therefore did not appear, so clicking Dismiss This Reminder and confirming suppression after dismissal were not verified live. No receipts or reminder preferences were changed to force a popup.

The preceding successful DesktopTests and SkillCatalogTests run covered 75 tests, including the dismissal wording, once-per-version/build/installation reminder policy, eligibility/deferred presentation, and skill overview detection. The app build and receipt checks also passed in this installation run. These automated results are distinct from live popup evidence.

## Preservation

All baseline source file hashes are unchanged. Git index was empty at verification. Installed runtime, sidecar, plugin tree, installation receipt, launch agent, Codex skills, Claude Code skills and Cursor plugin hashes/links are unchanged. The installed app matches its verified receipt. Supporting baseline and verification JSON were retained as local temporary evidence.
