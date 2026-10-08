---
title: Glyphs MCP v2
slug: /
---

Glyphs MCP **2.0.1** connects AI applications to Glyphs 4 through seventeen tools. A
small bridge handles live font access; a separate server prepares supported
jobs outside the editor and verifies explicit acceptance saves. Native Undo,
Redo and Revert remain part of the editing workflow.

This guide describes **2.0.1**, desktop build **56**, with coordinated sidecar and bridge product version **2.0.1**. Its skills catalog and focused setup views have passed local regression and desktop UI checks; the app and ZIP are signed and notarized locally. Final distribution and native qualification remain separate release checks. The public **2.0.0/build 55** release and its [qualification and limits](reference/release-qualification.mdx) remain unchanged. See [version and identity](reference/version-identity.mdx). Glyphs 3 uses the retained [v1 guide](/docs/) and separate v1.11.0 download.

## Start here

1. [Install the components](getting-started/installation.mdx) you want.
2. [Connect your AI application](getting-started/connect-client.mdx).
3. Try the [first session](tutorial/first-session.mdx) on a disposable font, using
   the [conversation workflow](tutorial/conversation-edits.mdx).

| Component | What it does |
| --- | --- |
| Glyphs MCP | Runs the local server, prepares jobs and applies reversible changes through the bridge. |
| Curve Inspector | Displays a curvature comb on the active layer. |
| Reference Inspector | Compares the active layer with Last Saved, a font file or a Git reference. |

Both inspectors are optional and can be installed without the MCP server. The installer includes their required dependencies.

## Available work

Prepare [spacing](spacing-tools.md), [collision kerning](kerning-workflow.md), a [first-pass slant](italic-first-pass.md), [start-node correspondence](workflows/start-node-correspondence.mdx), a width adjustment, closed native actions, compiler diagnostics or verified font exports. Review the typed result; apply mutations in Glyphs or publish artifact jobs only when the task authorizes it.

The [tool reference](reference/command-set.mdx) explains exact signatures and limits. The [migration guide](getting-started/migrate-from-v1.mdx) explains which v1 workflows are different or unavailable.

Created by **Thierry Charbonnel**. [Report an issue](https://github.com/thierryc/Glyphs-mcp/issues) or [support the project](https://github.com/sponsors/thierryc). The heart button in Glyphs opens a nonmodal Welcome/support panel with documentation, issue and support links. The local v2 desktop companion separately adds a six-slide first-launch introduction, replayable through **File → Welcome & Support** or the sidebar; Skip/Start setup opens Setup.
