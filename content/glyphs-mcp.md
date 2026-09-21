---
title: Glyphs MCP v2
slug: /
---

Glyphs MCP **2.0.0** connects AI applications to Glyphs 4 through nine tools. A
small bridge handles live font access; a separate server prepares supported
jobs outside the editor and verifies explicit acceptance saves. Native Undo,
Redo and Revert remain part of the editing workflow.

This guide describes the **signed and notarized local candidate**, desktop build **37**, bridge **(0.1.0)**. Public release is a separate step. For the released 1.11.0 workflow, use the [v1 guide](/docs/). The version selector keeps each guide's commands and setup separate.

## Start here

1. [Install the components](getting-started/installation.mdx) you want.
2. [Connect your AI application](getting-started/connect-client.mdx).
3. Try the [first session](tutorial/first-session.mdx) on a disposable font.

| Component | What it does |
| --- | --- |
| Glyphs MCP | Runs the local server, prepares jobs and applies reversible changes through the bridge. |
| Curve Inspector | Displays a curvature comb on the active layer. |
| Reference Inspector | Compares the active layer with Last Saved, a font file or a Git reference. |

Both inspectors are optional and can be installed without the MCP server. The installer includes their required dependencies.

## Available work

Prepare [spacing](spacing-tools.md), [collision kerning](kerning-workflow.md), a [first-pass slant](italic-first-pass.md), [start-node correspondence](workflows/start-node-correspondence.mdx), a width adjustment, closed native actions, compiler diagnostics or verified font exports. Review the typed result; apply mutations in Glyphs or publish artifact jobs only when the task authorizes it.

The [tool reference](reference/command-set.mdx) explains exact signatures and limits. The [migration guide](getting-started/migrate-from-v1.mdx) explains which v1 workflows are different or unavailable.

Created by **Thierry Charbonnel**. [Report an issue](https://github.com/thierryc/Glyphs-mcp/issues) or [support the project](https://github.com/sponsors/thierryc). The heart button in the extension panel opens Welcome & Support; its content is currently a placeholder.
