# Beta 4 validation record

Candidate: Glyphs MCP `2.0.0-beta.4`, desktop build 46, branch
`lit/v2-beta`.

Status: **published signed and notarized GitHub prerelease; signed update
acceptance complete**. The implementation begins at commit
`45eb12cbba9c8c57b905c4d396577c3ba4f2425a`; signed tag
`v2.0.0-beta.4` identifies qualification commit
`c09f10a1d6aeb0edc1c3e6b374a04af336dd1fd8`. Stable Latest remains v1.11.1,
separate from this prerelease.

## Source and visual-diff invariants

- [x] The Lean manifest and installation receipt expose one
  `glyphDiffReader` contract: schema 3, protocol API 1 and
  `glyphs_mcp_sidecar.glyph_diff_worker`.
- [x] The desktop selects only a fully validated bundled payload or an
  installed fallback whose receipt, sidecar and runtime identities match and
  whose paths contain no symlinks.
- [x] Packaging verification rejects missing geometry symbols, reader/schema
  mismatches, tampered identities and non-importable workers.
- [x] Schema 3 covers cubic and quadratic contours, decomposed components,
  open paths, component-inclusive bounds and partial per-layer warnings.
- [x] Canonical segment matching is independent of contour order and keeps
  inserted, deleted and moved-node changes localized.
- [x] Closed visible-outline failures are fatal to Visual and preserve Text;
  component and open-path failures remain nonfatal warnings.
- [x] The preview exposes an orange/blue reference/current legend, concise
  error categories, expandable technical details and a selected-glyph Retry.
- [x] Component fills are appearance-aware. Holding Space uses black in light
  mode and white in dark mode.

## Automated and native qualification

| Check | Result |
| --- | --- |
| Complete Python suite | 1,954 passed, 2 skipped; 4 warnings |
| Complete macOS/Xcode suite | Passed |
| Deterministic Lean payloads | Passed for arm64 and x86_64 |
| Private runtime startup | arm64 4.746 s; x86_64 9.936 s |
| Documentation production build | Passed |
| Unsigned app verification and release security | Passed |
| `git diff --check` | Passed |
| Glyphs 4 disposable-package acceptance | Cubic, quadratic, component, open path, anchor, width, added and deleted cases passed; source fixture unchanged |

The native acceptance ran in Glyphs 4 against disposable package copies. It
did not modify or save a user font.

## Signed artifacts

- [x] The payload, final application and disk image were accepted by Apple:
  `59152395-779e-4dfb-afa6-cc33317d2366`,
  `ac45ab8d-6cc9-40d0-bdf7-74ffa5cc57b5` and
  `cc8e9707-8451-4d50-98db-eadbfb1bd327`.
- [x] Stapler validation and Gatekeeper accept the application and DMG as
  Notarized Developer ID software from team `N9U29A4T8J`.
- [x] The extracted distribution verifies 88 Mach-O files, 47 signed bundles,
  installed-copy identities and the packaged schema-3 reader contract.
- [x] The signed Sparkle archive and appcast verify as Beta 4/build 46.

Published SHA-256 values:

```text
09c12429a49339627a167de7e3df040f7f6ece6495fea299942bb4671d175715  Glyphs-MCP-2.0.0-beta.4.dmg
37376b15aab286b4afb4210e59be943e0861dcbbc14260d6739fd7a9be937208  Glyphs-MCP-2.0.0-beta.4.zip
9b6136fc113514fc642646e08b32f9227e151c674f28129101d79268cb682e5a  appcast.xml
```

## Signed update and component migration

Acceptance ran in VirtualBuddy on macOS 26.6.2 arm64 with Glyphs 4.1 (4107).

- [x] A disposable build-45 fixture was Developer ID signed, notarized under
  submission `f6331d67-0c66-402a-844c-a50a3bfa5ed3`, stapled and accepted by
  guest Gatekeeper.
- [x] The previous installed Beta 3 app was moved to a timestamped backup.
- [x] Build 45 discovered the exact locally served signed Beta 4 appcast.
- [x] Sparkle downloaded the 143.5 MB archive, reported Ready to Install,
  installed it and relaunched the manager as Beta 4/build 46.
- [x] Guest Gatekeeper accepted the updated app. Its embedded feed was the
  production `lit/v2-beta/appcast.xml`; the temporary localhost override was
  removed.
- [x] Update All migrated the installed components. Reopening Glyphs restored
  Setup to Ready on port 9680.
- [x] Authenticated status returned release `2.0.0-beta.4`, build 46 and a
  reachable Glyphs 4 bridge. The running fingerprints matched the signed
  payload: sidecar
  `sha256:ba3672da1c70b16483a2c903337153df6a0ff4b75a7f6531485efa79895668cf`
  and bridge
  `sha256:08f1b0f10bd0f475c3180768592dd47c91d31ad8b39cc50f3cd73a44b65c942d`.

## Remaining manual coverage

Physical Intel acceptance and the broader fresh/partial/removal, ownership
conflict, absent-agent and every-client reload matrix remain unverified. These
are beta limitations, not inferred passes.

## Publication verification

- [x] The [Beta 4 GitHub release](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.4)
  is public, marked prerelease and contains the DMG, Sparkle ZIP, appcast and
  checksum file.
- [x] GitHub's asset digests match the exact locally verified published files.
- [x] The exact signed appcast was committed to `lit/v2-beta` after archive
  verification.
- [x] GitHub's stable Latest release remains v1.11.1.
