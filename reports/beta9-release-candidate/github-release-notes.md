## Glyphs MCP 2.0.0 Beta 9 · Build 51

### Changes

- Add **Beztrace** to the desktop app’s Setup component cards.
- Show plugin version, Glyphs and Python requirements, a link to the independent tracing engine, and instructions for **Path → Trace Image…**.
- Preserve the existing MCP, Curve Inspector, Reference Inspector and agent connection setup workflows.

**Beztrace is an informational development-preview card in this release.** Its separately versioned 0.1.0/build-2 plugin is unsigned and awaiting native qualification. The card does not install, update or remove it, and Install All excludes it. The Glyphs MCP app’s signing does not qualify or sign the external Beztrace plugin.

### Installation

Download `Glyphs-MCP-2.0.0-beta.9.dmg`, verify it with `SHA256SUMS`, and drag **Glyphs MCP.app** to Applications. Requires macOS 14 or later and Glyphs 4; supports Apple silicon and Intel. Glyphs needs its own Python environment selected in Settings → Addons.

Desktop updates and component updates are separate steps. In Setup, preserve current work and finish Glyphs’ normal save/quit prompts before changing components. Glyphs 3 continues to use its separate v1 release.

### Validation and known limits

The Beztrace card and details sheet were checked in the native desktop app; Escape closes the sheet. The complete local gate passed: **2,464 Python tests** (two skips), **220 desktop tests**, deterministic payloads, both private runtimes, package/skill checks and the documentation build. Distribution evidence is recorded in the Beta 9 validation notes.

The exact signed older-to-newer desktop update and component-migration trial, physical Intel/minimum-macOS acceptance, and narrow-window/dark-mode review remain unperformed. Beta 8’s unresolved group-pair native UI Undo and exact-pair card visual acceptance checks also remain open. This release adds no font-editing behavior and does not claim to resolve those limits.

This is a prerelease. Stable Latest remains v1.11.1.
