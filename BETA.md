# Glyphs MCP 2.0.0 Beta 1

**Status: preparing the beta. No public beta download is available yet.**

A native macOS workspace for connecting AI applications to Glyphs 4, managing
components, and starting font projects from templates. This is an early beta;
feedback will help shape version 2.0.0.

The planned release is **v2.0.0-beta.1**, desktop **build 43**, from `lit/v2-beta`.
Glyphs 3 stays on its separate, pinned 1.11.0 plugin.

## Download and requirements

When published, this page will link to the exact GitHub prerelease and its
`Glyphs-MCP-2.0.0-beta.1.dmg`. Until then, the unsigned local build is for
maintainer review only. The stable download remains available through
[GitHub Releases](https://github.com/thierryc/Glyphs-mcp/releases/latest).

Target requirements: macOS 13 or later, Apple silicon or Intel, and Glyphs 4
for the new bridge. The installer bundles private runtimes; terminal setup is
not required. The supported matrix must pass release qualification before the
beta is offered publicly. Your AI client is configured separately.

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

The beta keeps the existing application and service identity. It is not an
independent environment for running a second server beside a previous build.
Desktop updates and component installation are separate steps. For the
migration details, read [the migration guide](content/getting-started/migrate-from-v1.mdx).
A tested rollback procedure will be included with the public release.

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

Downloads will be open to everyone. Enrollment is optional: you do not need to
join a group to use the beta. Once the download is live, volunteers can use the
[prefilled enrollment issue](https://github.com/thierryc/Glyphs-mcp/issues/new?title=%5BBeta%20tester%5D%20I%27d%20like%20to%20help&body=macOS%20version%3A%0AApple%20silicon%20or%20Intel%3A%0AGlyphs%20version%3A%0AAI%20client%3A%0AWorkflows%20I%20can%20test%3A%0A%0AI%20would%20like%20to%20receive%20beta%20testing%20follow-ups%20in%20this%20GitHub%20issue.).
Issues are public; no email address or font upload is required.

The most useful first reports cover installation, client connection, template
refresh, project creation, inspector display and a complete apply/discard cycle.
Include your beta/build number, macOS, processor, Glyphs version, client, steps,
expected result and actual result. Share a minimal sample only if you can make
it public. [Report a beta issue](https://github.com/thierryc/Glyphs-mcp/issues/new?title=%5BBeta%202.0.0%5D%20&body=Beta%20and%20build%3A%0AmacOS%20and%20processor%3A%0AGlyphs%20version%3A%0AAI%20client%3A%0ASteps%3A%0AExpected%3A%0AActual%3A).

Known limitations: the welcome screen is still a placeholder; the seven-tool
workflow has a narrower scope than the legacy catalog. Cross-machine
installation, migration, rollback and signed update qualification are still
pending. This beta preparation adds no telemetry or mailing-list subscription.
