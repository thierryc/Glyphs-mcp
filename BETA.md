# Glyphs MCP 2.0.0 Beta 2

**Status: Beta 2 is available as a GitHub prerelease. The stable Latest release
remains v1.11.0.**

A native macOS workspace for connecting AI applications to Glyphs 4, managing
components, and starting font projects from templates. This is an early beta;
feedback will help shape version 2.0.0.

The release is **v2.0.0-beta.2**, desktop **build 44**, from `lit/v2-beta`.
Implementation and qualification evidence is recorded in
[BETA2-VALIDATION.md](BETA2-VALIDATION.md).
Glyphs 3 stays on its separate, pinned 1.11.0 plugin.

## Download and requirements

[Download Glyphs MCP 2.0.0 Beta 2](https://github.com/thierryc/Glyphs-mcp/releases/download/v2.0.0-beta.2/Glyphs-MCP-2.0.0-beta.2.dmg),
or review the complete [Beta 2 prerelease](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.2)
and its `SHA256SUMS` before installing. The stable download remains available
through [GitHub Releases](https://github.com/thierryc/Glyphs-mcp/releases/latest).

Target requirements: macOS 14 or later, Apple silicon or Intel, and Glyphs 4
for the new bridge. The installer bundles private runtimes; terminal setup is
not required. The signed app and DMG are notarized and accepted by Gatekeeper;
both packaged architectures passed automated qualification. Your AI client is
configured separately.

## First session

1. Make a duplicate of a font for testing. Keep the original and your existing
   application available while evaluating the beta.
2. Open the beta app and choose **Components**. Select your Glyphs version and
   the components you want. Follow the app's instruction to quit Glyphs before
   applying component changes, then reopen Glyphs.
3. In **Overview**, verify the server status. Connect an AI client using the
   address shown by the app. Avoid running a second MCP server on the same port.
4. In **Project**, create a disposable project from the bundled starter or a
   public template. Use **Refresh** to retrieve the current beta template list.
5. On your font copy, prepare a small supported spacing or kerning job, inspect
   its report, then apply or discard it. Check native Undo and Redo before Save.
6. In a Git-backed project, select a changed text file and try unified, split,
   wrapping and copying. For a changed file under
   `.glyphspackage/glyphs/`, switch between **Visual** and **Text**, select a
   layer, and inspect the Before/Both/After overlays. Confirm unchanged geometry
   is neutral, the reference is mint and only the geometric delta fill is cyan.
   Exercise previous/next difference, Reset, Command zoom shortcuts, pinch,
   Option-scroll and Z-click zoom. Hold Space for the black silhouette preview.
   These
   previews are read-only and do not stage, edit or comment on files.

The beta keeps the existing application and service identity. It is not an
independent environment for running a second server beside a previous build.
Desktop updates and component installation are separate steps. For the
migration details, read [the migration guide](content/getting-started/migrate-from-v1.mdx).
To roll back, finish or discard pending jobs, remove the Beta 2 components in
the app, then reinstall the previous stable release. Keep font and settings
backups until the beta workflow has been accepted for your environment.

## Components

### Glyphs MCP

Connect an AI client to Glyphs 4. The seven tools inspect documents and prepare,
review, apply or discard supported jobs. There is no arbitrary Python tool.
See the [tool contract](content/reference/command-set-v2.mdx).

### Curve Inspector

Inspect curve geometry and handles directly on the canvas.

### Reference Inspector

Compare outlines and spacing with a reference such as the last saved version,
another font file or a Git revision. See
[desktop component documentation](content/getting-started/desktop.mdx).

## Templates and updates

The beta uses `templates/registry.json` on `lit/v2-beta` and a separate template
cache. A registry update can change the available list without reinstalling
the app. It takes effect when you refresh; it does not change existing projects.
If the registry is unavailable, the app retains the cached or bundled list.
Public template archives are pinned to a commit and checksum.

Beta app updates use a separate feed on the same beta branch. Automatic checks
are optional. A stable release will require an explicit release decision and
a new build; this beta will not silently become the final release.

## Help test the beta

Downloads are open to everyone. Enrollment is optional: you do not need to
join a group to use the beta. Volunteers can use the
[prefilled enrollment issue](https://github.com/thierryc/Glyphs-mcp/issues/new?title=%5BBeta%20tester%5D%20I%27d%20like%20to%20help&body=macOS%20version%3A%0AApple%20silicon%20or%20Intel%3A%0AGlyphs%20version%3A%0AAI%20client%3A%0AWorkflows%20I%20can%20test%3A%0A%0AI%20would%20like%20to%20receive%20beta%20testing%20follow-ups%20in%20this%20GitHub%20issue.).
Issues are public; no email address or font upload is required.

The most useful first reports cover installation, client connection, template
refresh, project creation, source and glyph diff display, inspector display and
a complete apply/discard cycle.
Include your beta/build number, macOS, processor, Glyphs version, client, steps,
expected result and actual result. Share a minimal sample only if you can make
it public. [Report a beta issue](https://github.com/thierryc/Glyphs-mcp/issues/new?title=%5BBeta%202.0.0%5D%20&body=Beta%20and%20build%3A%0AmacOS%20and%20processor%3A%0AGlyphs%20version%3A%0AAI%20client%3A%0ASteps%3A%0AExpected%3A%0AActual%3A).

Known limitations: the welcome screen is still a placeholder; the seven-tool
workflow is materially narrower than the legacy catalog and exposes no
arbitrary Python tool. Visual diffs cover individual `.glyph` files under
`.glyphspackage/glyphs/`, not monolithic `.glyphs` files, and require a
compatible Glyphs 4 runtime. There is no diff editing, staging, commenting or
all-layers grid. Both architectures are packaged and automatically verified,
but this final build was not exercised on physical Intel hardware. The final
DMG passed mounted and extracted-install verification; an additional
VirtualBuddy guest retest was blocked because that VirtualBuddy build disables
file transfer. An end-to-end Beta 1 → Beta 2 Sparkle update trial remains to be
recorded. The beta adds no telemetry or mailing-list subscription.

Final SHA-256 checksums:

- DMG: `35faebedd0d4a36b64fac2fec5c7d0871843e22d86a5828646c64bed508c0291`
- Sparkle ZIP: `9af495f4e4d834088df8d99e6a14a6faa3ed5f87137217b2f35f963ea9e7e532`
- Signed appcast: `a1b088f0cb8a533eb4a44b0507d9b2996b13c7cfc9459010596b3e42468bd61d`
