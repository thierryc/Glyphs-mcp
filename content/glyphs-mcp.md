---
title: Glyphs MCP v2
slug: /
---

Glyphs MCP **2.2.0/build 64 (in preparation)** connects AI applications to Glyphs 4 through twenty-one data/action tools and one optional read-only card-display tool. A small bridge handles live font access; a separate server prepares supported jobs. Already-authorized scripts run after preparation without a forced Save; recovery preserves the full pre-run font state within the current Glyphs session. Explicit preview requests still wait. Native Undo, Redo and Revert remain available.

Version 2.2.0 adds Tasks with open workflows, blockers, conversation handoff and guarded recovery for abandoned work. Cleared closed-history summaries have a protected 30-day retention policy. Project diffs compare PNG, JPEG and WebP files with Before / Both / After, a draggable divider and native zoom controls. The published stable release remains 2.1.0/build 63; 2.2.0 has not been published or qualified as a signed distribution.

Open Edit tabs and create independent unsaved document copies directly. Update the bridge and sidecar together through Setup. See [qualification and limits](reference/release-qualification.mdx) and [version and identity](reference/version-identity.mdx). Glyphs 3 uses the retained [v1 guide](/docs/).
Compiled [font comparisons](workflows/font-comparison.mdx) use the optional
Diffenator runtime and can run without an open Glyphs document.

## Start here

1. [Install the components](getting-started/installation.mdx) you want.
2. [Connect your AI application](getting-started/connect-client.mdx).
3. Try the [first session](tutorial/first-session.mdx) on a disposable font, using
   the [conversation workflow](tutorial/conversation-edits.mdx).

| Component | What it does |
| --- | --- |
| Glyphs MCP | Runs the local server, prepares jobs and applies reversible changes through the bridge. |
| Curve Inspector | Displays a curvature comb and repairs eligible joins with native stars or regular nodes. |
| Reference Inspector | Compares the active layer with Last Saved, a font file or a Git reference. |

Both inspectors are optional and can be installed without the MCP server. The installer includes their required dependencies.

## Available work

Prepare [spacing](spacing-tools.md), [collision kerning](kerning-workflow.md), a [first-pass slant](italic-first-pass.md), [start-node correspondence](workflows/start-node-correspondence.mdx), a width adjustment, closed native actions, compiler diagnostics or verified font exports. Review the typed result; apply mutations in Glyphs or publish artifact jobs only when the task authorizes it.

The [tool reference](reference/command-set.mdx) explains exact signatures and limits. The [migration guide](getting-started/migrate-from-v1.mdx) explains which v1 workflows are different or unavailable.

Created by **Thierry Charbonnel**. [Report an issue](https://github.com/thierryc/Glyphs-mcp/issues) or [support the project](https://github.com/sponsors/thierryc). The heart button in Glyphs opens a nonmodal Welcome/support panel with documentation, issue and support links. The local v2 desktop companion separately adds a six-slide first-launch introduction, replayable through **File → Welcome & Support** or the sidebar; Skip/Start setup opens Setup.
