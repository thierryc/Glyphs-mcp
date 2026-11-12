# Native app localization validation — 12 November 2026

## Delivered changes

The native application retains its `.strings` architecture and now ships English (`en`), French (`fr`), Simplified Chinese (`zh-Hans`), German (`de`), Spanish (`es`), and Brazilian Portuguese (`pt-BR`). Each language contains 1,408 unique translation keys and four `.stringsdict` entries for days, unread tasks, changed files, and open-font warnings. Existing French and Chinese tables were completed; German, Spanish, and Brazilian Portuguese were translated with GPT-6.1 Sol subagents.

Native presentation now resolves Core messages from the main app bundle, with bundle and locale injection for tests. Structured errors preserve the English diagnostic and external details while translating their app-owned presentation. Process failures and timeouts have typed cases; Git timeout handling no longer depends on an English substring. Timeout durations use localized measurement formatting. Dynamic UI messages, accessibility labels, file-panel titles, built-in template presentation, status labels, and date/count presentation were audited and corrected.

Xcode includes all six locale resource directories and plural tables. The built application's development region is explicitly `en`. macOS language selection remains in charge; no in-app selector or public MCP schema change was introduced.

Pre-existing working-tree edits were retained. Documentation, remote catalog descriptions, skill/template file contents, embedded MCP web UI, and raw diagnostic output were not translated. Installation, signing, publication, and restarts of the installed app or server were not performed.

## Automated validation

The Swift and Python results below include the timeout-formatting correction. A subsequent resource-only German wording refinement was rebuilt and checked against the source catalogs and bundle verifier.

- Swift scheme `GlyphsMCPInstaller`: 355 tests passed, zero failures.
- Focused Python desktop localization/build/process/catalog tests: 55 passed.
- Source tables: all six locales pass duplicate, empty, missing-key, malformed resource, plural metadata, and format argument checks. Positional reordering and escaped literal percent signs are covered.
- Compiler-emitted `.stringsdata`: all extracted native keys exist in the catalog.
- Explicit localization helper and folder-panel title calls: checked against the English catalog, with a regression test for an untranslated native panel title.
- Built app: all six translation and plural resources match source; development region is English; full desktop bundle verification passes.
- `git diff --check`: passed.

Swift tests cover injected bundles, structured error presentation with unchanged paths and external diagnostics, literal percent signs, zero/one/multiple plural counts, regional language matching, unsupported-language English fallback, and localized timeout units. Python tests also exercise compiled binary resource validation and reject stale bundle translations.

Reproduce the focused checks from the repository root:

```sh
python3 scripts/check_desktop_localizations.py
python3 -m pytest -q src/glyphs-mcp/tests/test_desktop_localizations.py src/glyphs-mcp/tests/test_desktop_build.py src/glyphs-mcp/tests/test_desktop_process_pool.py src/glyphs-mcp/tests/test_skill_catalog_package.py
PYTHON_BIN=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3 xcodebuild test -project macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj -scheme GlyphsMCPInstaller -configuration Debug -destination 'platform=macOS' -derivedDataPath /tmp/gmcp-localization-derived CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO SWIFT_EMIT_LOC_STRINGS=YES PYTHON_BIN=/Library/Frameworks/Python.framework/Versions/3.14/bin/python3
python3 scripts/check_desktop_localizations.py --app '/tmp/gmcp-localization-derived/Build/Products/Debug/Glyphs MCP.app' --extracted /tmp/gmcp-localization-derived/Build/Intermediates.noindex
python3 scripts/verify_desktop_app.py '/tmp/gmcp-localization-derived/Build/Products/Debug/Glyphs MCP.app'
```

Local artifacts:

- Unsigned app: `/tmp/gmcp-localization-derived/Build/Products/Debug/Glyphs MCP.app`
- Swift test/build log: `/tmp/gmcp-localization-xcode.log`
- Final resource-only rebuild log: `/tmp/gmcp-localization-final-build.log`
- Python test log: `/tmp/gmcp-localization-pytest.log`
- Bundle verification metadata: `/tmp/gmcp-localization-bundle.json`

## Native UI review

Separate temporary copies with unique bundle identifiers were used to avoid replacing or restarting the installed manager. Each review copy retained one locale and set that locale as its development region. This exercised native SwiftUI/AppKit presentation without changing the user's system or per-app language preferences. Standard language preference matching and fallback were tested separately in Swift. All launched review copies were quit after inspection.

| Language | Native surfaces inspected |
| --- | --- |
| English | Welcome, Setup, sidebar, accessibility tree, menu-bar labels |
| French | Welcome, Setup accessibility, Settings, sidebar |
| German | Welcome, Setup, Skills, Tasks, Settings, sidebar |
| Spanish | Welcome, Setup, sidebar |
| Brazilian Portuguese | Welcome, Setup, project catalog, starter template preview, native Open Project panel, sidebar |
| Simplified Chinese | Welcome, Setup, Settings, sidebar |

The review found and fixed clipped static sidebar labels, an English task outcome, an English built-in skill description, an untranslated starter-template preview name, and missing file-panel title keys. The rebuilt Portuguese app visibly confirmed sidebar wrapping and the corrected template subtitle. The final panel-title additions were validated in source and the compiled bundle; the panel was not reopened after those resource-only additions.

## Outstanding acceptance review

The implementation and automated checks are complete, but the requested exhaustive screen-by-screen visual acceptance matrix is **not complete**. The table above is the actual coverage, not a claim that every dialog, menu, tooltip, accessibility label, narrow-window size, notification, project/Git state, and update/error flow was visually exercised in all six languages. Those remaining visual cases need review before claiming full visual acceptance. Install/update execution and live font mutation were deliberately not used to manufacture those states.

Translation terminology and meaning were reviewed separately from structural checks by the translation agents, with additional in-context inspection during native review. Independent native-speaker review remains outstanding, particularly for specialized font terminology and long German/Portuguese text. Matching key counts is not evidence of linguistic approval. Existing French and Chinese wording was preserved where possible and has not received a fresh independent linguistic sign-off.

The final read-only Sol review of the late entries across all five translated locales identified a German distinction between choosing an existing project folder and choosing a new project's location. The location title was refined to “Speicherort für das Projekt auswählen”. The other late entries passed that semantic review.
