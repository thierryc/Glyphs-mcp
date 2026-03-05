# Translation Review & Editing Guide

This repo ships user-facing UI in two places:

1) **Glyphs plug‑in UI** (menu items, windows, alerts) — translated via `Glyphs.localize(...)`.
2) **macOS Installer app** (SwiftUI + AppKit panels/alerts) — translated via `Localizable.strings`.

This document is for contributors who review and edit the translations (French, Chinese, etc.).

## Supported languages (current)
- English: `en` (source / fallback)
- French: `fr`
- Simplified Chinese: `zh-Hans`

## 1) Glyphs plug‑in translations

### Where strings live
Edit translations in the **source plug‑in bundle**:

- `src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Resources/i18n.py`

The Plugin Manager bundle is generated from that source. Do **not** hand-edit translations inside `plugin-manager/…` unless you know exactly why.

After editing, re-sync the Plugin Manager bundle:

```bash
./scripts/build_plugin_manager_bundle.sh
```

### How localization works (official Glyphs behavior)
Glyphs uses `Glyphs.localize({ languageCode: "…" })`. Internally it:

- walks `Glyphs.defaults["AppleLanguages"]` in order,
- tries exact matches first (e.g. `zh-Hans-CN`),
- then repeatedly strips subtags (e.g. `zh-Hans-CN → zh-Hans → zh`),
- falls back to `"en"` if present.

**Important implication for Chinese:**
Do **not** add a generic `zh` entry while only shipping Simplified Chinese.
Otherwise Traditional users (`zh-Hant…`) can fall back to `zh` and incorrectly see Simplified. Add `zh` only when it’s genuinely language-agnostic, or add `zh-Hant` first.

### Editing translations
In `i18n.py` you’ll see a `STRINGS` dictionary keyed by stable IDs (example: `menu.start`, `status.running`, …). Each entry is a dict of language codes.

Guidelines:
- Keep the English string (`"en"`) present for every key.
- Preserve **placeholders** exactly:
  - Python `.format()` placeholders use `{name}` (examples: `{port}`, `{url}`, `{error}`).
  - Don’t translate or remove the braces; you can move them in the sentence.
- Preserve line breaks when present (`\n` / `\n\n`), especially in alert bodies.
- Prefer short UI labels; avoid adding trailing punctuation unless it’s already present.

### What is (and isn’t) localized
Localized:
- Menu items
- Plug‑in window titles/labels/buttons
- Alerts and user-facing error messages

Not localized (by design, for now):
- Debug logs printed to the console
- Technical tool output

### Testing the plug‑in translations
1) Install the plug‑in bundle into Glyphs.
2) Switch Glyphs UI localization (Glyphs app setting) / macOS language as needed.
3) Restart Glyphs and verify:
   - **Edit menu** items for the plug‑in
   - Status window and port-busy prompts

## 2) Installer app translations (macOS)

### Where strings live
Installer translations live in:

- `macos-installer/GlyphsMCPInstaller/Resources/fr.lproj/Localizable.strings`
- `macos-installer/GlyphsMCPInstaller/Resources/zh-Hans.lproj/Localizable.strings`

English is the source language; most keys are the literal English UI strings, so:

- `macos-installer/GlyphsMCPInstaller/Resources/en.lproj/Localizable.strings`

is intentionally minimal.

### How localization works (SwiftUI + AppKit)
- Many SwiftUI calls like `Text("…")`, `Button("…")`, `GroupBox("…")` automatically look up the string in `Localizable.strings`.
- Some dynamic/AppKit strings use `NSLocalizedString(...)` and `String(format: ...)` so they can be translated (alerts, open panels, “Error: %@”, etc.).

**Important implication for translators:**
The English phrase is usually the lookup key. If developers change English UI copy, it may invalidate translations until the `.strings` files are updated.

### Editing translations
`Localizable.strings` format is:

```strings
"Key in English" = "Translation";
```

Guidelines:
- Preserve all format placeholders:
  - `%@` for strings (and `%d`, `%ld`, etc. if present).
  - The translated string must contain the **same placeholders** as the key, with the same count.
- Escape quotes as `\"`.
- Keep `\n` line breaks if present (especially alert bodies).
- Keep menu arrows / symbols exactly (`→`, ellipsis `…`, non-breaking hyphens if present).

### Adding a new language later
To add a new language (example: `de`):
1) Add a new folder `Resources/de.lproj/Localizable.strings`.
2) Add the new localization to the Xcode project (variant group + `knownRegions`).
3) Build to confirm resources are embedded.

### Testing the installer translations
Build the installer app:

```bash
./scripts/build_installer_app.sh
```

Then test language selection:
- macOS supports per-app language overrides in Finder (**Get Info → Language**) for an app bundle.
- Advanced: you can set app language via defaults using the bundle id `cx.ap.glyphsMcpServerInstaller`.

## 3) Quick “translator sanity checklist”
- No missing placeholders (`{port}` / `%@`) after editing.
- No accidental “smart quotes” issues in `.strings` (quotes must be ASCII `"` with escaping).
- UI labels remain reasonably short (buttons shouldn’t wrap unnecessarily).
- Chinese punctuation is consistent (don’t mix fullwidth/halfwidth randomly).
- Run the build scripts to ensure nothing broke:
  - `./scripts/build_plugin_manager_bundle.sh`
  - `./scripts/build_installer_app.sh`
