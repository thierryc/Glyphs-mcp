# Beta 5 validation record

Candidate: Glyphs MCP `2.0.0-beta.5`, desktop build 47, branch
`lit/v2-beta`.

Status: **local signed and notarized candidate; signed update acceptance and
component migration complete; not published**. No Beta 5 tag, GitHub release,
asset upload, appcast publication or announcement was created. Stable Latest
remains v1.11.1.

## Automated qualification

| Check | Result |
| --- | --- |
| Complete Python suite | 2,073 passed, 1 skipped; 5 warnings |
| Complete macOS/Xcode suite | 203 passed |
| Deterministic Lean payloads | Passed for arm64 and x86_64 |
| Signed private runtime startup | arm64 4.201 s; x86_64 9.465 s |
| Private runtime interface | Nine MCP tools over HTTP and stdio; no package downloads |
| Documentation, skill mirrors and release security | Passed |
| Unsigned build-47 verification | Passed |

The release gate covered native actions, feature compilation, static/variable/
web export, deterministic state hashes, guarded apply/accept/discard, native
Undo/Redo, worker isolation and the nine-tool public contract.

## Signed artifacts

- [x] The embedded payload, final application and disk image were accepted by
  Apple's notary service under submissions
  `23ca96b2-aaba-4989-8b43-d8e75d58dbf6`,
  `4dd15d22-b91c-4ba8-ace6-cd6cfd154069` and
  `aebd55cd-1e6d-4846-bbf1-8c44a7b80aa1`.
- [x] The application and DMG pass signature, timestamp, stapler and Gatekeeper
  checks as Notarized Developer ID software.
- [x] The signed universal payload verifies 94 Mach-O files and 47 signed
  bundles.
- [x] The Sparkle archive and appcast identify Beta 5/build 47.

Local candidate SHA-256 values:

```text
cadfadac6779eeb0e2051f1c0b8c2feba1010ef4a8f43709594729f732e4c9eb  Glyphs-MCP-2.0.0-beta.5.dmg
a197164a39f2cbe9a882ba987e61a96233da00bea6767637708e8b49a7d03466  Glyphs-MCP-2.0.0-beta.5.zip
840d35b4d0dfe079b1b1a08234b25f71331c7be14620ddaccd004fb78ae24d31  appcast.xml
```

These files remain private local artifacts. The values above are not claims
about a public download.

## Host installation

Acceptance ran on macOS 26.7.1 arm64 with Glyphs 4.1 (4107).

- [x] The exact notarized app was installed as `/Applications/Glyphs MCP.app`;
  its embedded payload is byte-identical to the qualified candidate.
- [x] The previous build-45 app was retained at
  `/Applications/Glyphs MCP 2.0.0-build45 backup.app`.
- [x] All three Glyphs components and the Claude Desktop connection updated.
  Modified or unowned Codex and Claude Code skills were preserved and reported
  as ownership conflicts rather than overwritten.
- [x] Glyphs reopened and Setup reached Ready on port 9680.
- [x] Authenticated status reports Beta 5/build 47, a reachable Glyphs 4 bridge,
  all nine job kinds, 17 qualified native actions, feature compilation, static/
  variable/web export and both verification capabilities.
- [x] The running installation receipt matches sidecar
  `sha256:4717b0106723c4a7c8cf0d0b224a23d654bf79c4f880e223c8521e043e20a0f2`
  and bridge
  `sha256:a94c73759756169a8fc308d1c0ea9f689d4975283139c73c6706e1eb09387903`.

## Signed update and component migration

Acceptance ran in VirtualBuddy on macOS 26.6.2 arm64 with Glyphs 4.1 (4107).

- [x] A disposable build-46 fixture was Developer ID signed, notarized under
  submission `df81297a-e3c2-411c-ba54-8be4a57681f1`, stapled and accepted by
  guest Gatekeeper.
- [x] Build 46 discovered the exact locally served signed Beta 5 appcast.
- [x] Sparkle downloaded the 153.6 MB signed archive, reported Ready to Install,
  installed it and relaunched the manager as Beta 5/build 47.
- [x] The updated app restored the production
  `lit/v2-beta/appcast.xml` feed; the temporary localhost feed was removed.
- [x] Update All migrated the installed components. Reopening Glyphs restored
  Setup to Ready on port 9680.
- [x] Guest signature and Gatekeeper checks passed. Authenticated status
  reported the nine job kinds, 17 native actions and seven compile/export/
  verification capabilities with the same receipt and live identities as the
  signed candidate.
- [x] The temporary guest and host update-feed processes were stopped. The
  upgraded Beta 5 app remains installed for font-work testing.

## Remaining manual coverage

Physical Intel acceptance and the broader fresh/partial/removal, ownership
conflict, absent-agent and every-client reload matrix remain unverified. These
are beta limitations, not inferred passes. Publication remains a separately
authorized release operation.
