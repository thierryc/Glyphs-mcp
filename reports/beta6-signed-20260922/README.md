# Beta 6 signed-distribution qualification

Candidate: `2.0.0-beta.6`, build 48; functional source `67b70ae3`.

- `private-runtimes.json`: signed arm64 and x86_64 packaged installer CLI,
  HTTP/stdio tool inventory, MCP App resource and result checks, without downloads.
- `dimensions-native.json` and `dimensions-native.log.gz`: all 204 checks passed
  using the signed packaged bridge/protocol/sidecar and CLI, in an isolated
  Glyphs 4.1 (4107) process with disposable fonts.

The native harness is `scripts/qualify_dimensions_native.py`, with only its
module search roots redirected to the extracted signed payload and its output
redirected to `build/beta6-signed-dimensions`. The installed host MCP and the
user's font were not touched by this isolated check.

Desktop update, component migration, artifact verification and GitHub
publication passed. `publication.json` records unauthenticated public downloads
and their checksums; stable Latest remains v1.11.1.


## Signed update rejection checks

The existing VirtualBuddy guest (macOS 26.6.2, arm64) ran the verified build-46
fixture with a signed local feed targeting the final Beta 6 app. The manager
remained available after each rejected update:

- A tampered feed produced “The update feed is improperly signed and could
  not be validated.”
- A signed feed with an invalid archive signature downloaded the archive,
  then produced “The update is improperly signed and could not be validated.”
- An interrupted archive response (65,536 bytes of the advertised full length)
  produced “An error occurred while downloading the update.”

Each error was cancelled before checking the next signed fixture. The valid
update and component migration follow these failures in the same VM session.

The DMG layout is generated directly with ds-store 1.3.3 and mac-alias 2.2.3.
The final immutable image is mounted read-only and its icon locations,
112px icon size, TIFF background and 680×448 window bounds are asserted before
signing/notarization. This replaces only the build script's Finder AppleScript
step for this run. These packaging-only libraries are not shipped in the app.


## Successful update and migration

- The same VM then downloaded the valid 153.6 MB signed archive, reached
  **Ready to Install**, installed it and relaunched **Beta 6/build 48**.
- The new app restored the production `lit/v2-beta/appcast.xml` feed.
- **Quit Glyphs**, then **Update All**, migrated the existing Beta 5 components.
  Reopening Glyphs restored **Setup → Ready** on port 9680.
- `guest-result.json` records successful guest codesign/Gatekeeper checks,
  build 48, twelve tools, ten job kinds, 17 native actions, worker availability,
  and receipt/live sidecar and bridge identities matching the signed payload.
- The temporary guest feed and host download servers were stopped; the upgraded
  app and components remain in the VM.
- `tested-app-files.json` preserves all 96 regular files and symlinks in the
  update-tested application. The publisher may regenerate the ZIP container;
  the extracted application must remain identical.
- Apple accepted the expanded payload, desktop app and final DMG; their three
  `notary-*.json` receipts are included. All nested signatures, stapled tickets,
  Gatekeeper and signature-preserving payload installation checks passed.
- The final disk image's background, app icon and Applications target were
  visually checked through Finder on a read-only mount. Its persisted metadata
  was independently verified before signing.

The first DMG attempt was discarded before publication because Finder's late
metadata flush replaced its layout. Submission
`42f4db32-3135-4843-b263-a25e018db305` is not a release artifact. Only the corrected
image under accepted submission `4b164bfa-ab73-4c83-b976-9b688477c91a` is qualified.

Physical Intel hardware and the broader manual/client scenario matrix remain
unverified beta coverage. x86_64 runtime qualification ran under Rosetta on the
Apple-silicon host. Cancellation of a dirty-font closure and deliberate failed
component migration were not newly exercised in this VM session.


## Publication

The guarded publisher reran the complete local gate and verified all four
GitHub asset digests before publishing the prerelease. Independent
unauthenticated downloads match the verified local bytes and published
SHA256SUMS. The public ZIP's extracted signed/stapled application matches all
96 files and links in the update-tested application. The exact signed appcast
was copied to the beta branch only after those download checks passed.

The updated publication documentation passed its production build;
`publication-docs-build.log.gz` records the result.
