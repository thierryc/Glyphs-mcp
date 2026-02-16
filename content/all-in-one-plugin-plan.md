# All‑in‑One “Glyphs MCP Pro” Plugin (Future Separate Repository Plan)

This document is a **decision-complete implementation plan** for a future, separate repository that can be **sold/distributed under a commercial/proprietary license**, while staying compatible with the open-source `Glyphs-mcp` server project.

It intentionally focuses on **setup simplicity** and **user-facing productivity features** inside Glyphs.

> Note: This is practical guidance, not legal advice.

---

## Goals

- **One ZIP install** for end users (drag-and-drop onto Glyphs, or install via Plugin Manager if you choose to distribute that way).
- **Simplified MCP setup**:
  - Start server from a menu item in Glyphs.
  - Copy endpoint + copy auth token (if used).
  - Clear status of “running / not running”.
- **Embedded helper features** that reduce friction:
  - Set font/master Custom Parameters for spacing tuning (`gmcpSpacing*` keys).
  - Copy/paste prompt snippets for common MCP clients.
  - Simple “health check” and tool list viewer.

---

## Non-goals

- No references to external spacing projects in user docs.
- Do **not** auto-save fonts. Any write operation should be explicit and user-controlled.
- Avoid mutating outlines unless the user explicitly confirms.
- Do not attempt to replace Glyphs’ native spacing/kerning UI; this is an accelerator, not a replacement.

---

## Repository layout (new repo)

Recommended top-level structure:

- `Glyphs MCP Pro.glyphsPlugin/`
  - General plugin that:
    - embeds and runs an MCP server (HTTP)
    - exposes menu items + panels
    - provides “Spacing Params…” editor UI
    - provides “Prompt Snippets…” UI
    - provides “Server Status…” UI
- Optional: `Glyphs MCP Pro Tools.glyphsReporter/`
  - Reporter overlay toggles (View menu) for lightweight in-editor readouts (optional; not required for the first release)
- `LICENSE` (commercial/proprietary)
- `THIRD_PARTY_NOTICES.md`
  - must include license texts/notices for bundled third-party code (Apache/MIT/BSD, etc.)
- `README.md` (end-user installation and usage)
- `DEVELOPMENT.md` (build/release instructions for you)

---

## Licensing guidance (practical)

### When bundling Apache-2.0 / MIT / BSD dependencies

If you vendor third-party code inside the plugin bundle:

- Keep the original license text and attribution (typically in `THIRD_PARTY_NOTICES.md`).
- If a dependency includes a `NOTICE` file (Apache-2.0), include its required contents as well.
- Don’t remove existing copyright headers.

### When reusing code from the open-source Glyphs MCP server repo

If you copy code from an Apache-2.0 repository into the commercial repository:

- Keep the Apache-2.0 `LICENSE` text available to recipients for the copied portions (often via `THIRD_PARTY_NOTICES.md`).
- Keep attribution notices for any copied files.
- Mark modified files with a clear “you changed this” notice if required by the upstream license policy you are following.

**Recommendation:** keep the commercial repo’s proprietary code clearly separated from any vendored OSS code:

- `vendor/` for third-party code (unchanged)
- `src/` for proprietary code

---

## Dependency strategy options (for an all-in-one plugin)

The all-in-one plugin’s primary promise is “works on a clean machine”.

### Option A (primary): Bundle dependencies (vendored pure Python)

- Put required Python packages under:
  - `Glyphs MCP Pro.glyphsPlugin/Contents/Resources/vendor/…`
- Ensure the plugin `plugin.py` prepends that vendor path to `sys.path` before imports.

Pros:
- Zero setup for users
- No pip failures
- Works offline

Cons:
- Larger ZIP
- You must maintain third-party notices
- Must validate compatibility with Glyphs’ Python runtime versions

### Option B: Auto-install wizard

On first run, offer a guided “Install dependencies” action:

- installs into `~/Library/Application Support/Glyphs 3/Scripts/site-packages`
- verifies imports
- shows clear error messages and remediation steps

Pros:
- Smaller plugin ZIP
- Easier to update dependencies

Cons:
- More moving parts
- Requires network access and a working pip environment

### Option C: No external deps

Keep the “Pro” plugin UI-only and talk to an OSS server plugin installed separately.

Pros:
- Simplest licensing story
- Small bundle

Cons:
- Not “all-in-one”

**Default choice for “All‑in‑One”:** Option A (Bundle deps).

---

## UI/UX spec

### Menu items (Edit menu)

- `Start MCP Server`
- `Stop MCP Server` (or toggle state)
- `Server Status…`
  - shows:
    - running state
    - endpoint URL
    - token state (if used)
    - tool count + searchable tool list
  - buttons:
    - `Copy Endpoint`
    - `Copy Token` (only if present)
- `Prompt Snippets…`
  - list of preset prompt templates:
    - “Connect to MCP endpoint”
    - “Spacing workflow (review → apply)”
    - “Set spacing params and save”
  - each snippet has `Copy` and optionally “Paste into Macro Panel” (if you support it)
- `Spacing Params…`
  - editor for:
    - font-level defaults
    - per-master overrides
  - fields:
    - `area`, `depth`, `over`, `frequency`
  - key scheme:
    - write canonical keys:
      - `gmcpSpacingArea`
      - `gmcpSpacingDepth`
      - `gmcpSpacingOver`
      - `gmcpSpacingFreq`
    - optional toggle: “Write legacy keys too” (default OFF)
  - actions:
    - `Apply to Font`
    - `Apply to Selected Master`
    - `Apply to All Masters`
    - `Copy JSON preset` (for reproducible setups)

### Optional (View menu) overlay (Reporter plugin)

If/when added:

- `View → Show Spacing Params (MCP Pro)`
  - overlays effective values and their source (master vs font) in Edit View

---

## Technical spec

### Embedded server approach

- Run FastMCP server in a daemon thread from within Glyphs (same pattern as the OSS plugin).
- Default host/port: `127.0.0.1:9680` (configurable).
- Security:
  - optional static token authentication (off by default, on for teams)
  - origin validation
  - discovery endpoint enabled

### Persistence rules

- Any tool that mutates font data must:
  - require explicit confirmation in the UI (button click)
  - never auto-save the font file

### Safety constraints

- For tools that apply spacing or modify metrics, require a “dry run” preview step and an explicit confirmation step (mirroring the MCP `apply_spacing` safety gate).
- Skip combining marks and other unsafe categories by default.

---

## Acceptance checklist

- Fresh install on a clean machine:
  - user can start the server inside Glyphs in under 2 minutes
  - server status panel clearly shows endpoint and running state
- Spacing parameter editor:
  - sets font-level parameters and per-master overrides
  - values are visible in Glyphs UI in `File → Font Info…`
- Prompt snippets:
  - copy/paste works and is understandable without any external context
- Distribution compliance:
  - `THIRD_PARTY_NOTICES.md` exists and includes all required license texts/attributions for bundled code

