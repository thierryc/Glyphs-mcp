---
name: glyphs-mcp-maintainer-feedback
description: Collect bounded reproduction evidence for a Glyphs MCP issue.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs-mcp-maintainer-feedback

Use existing reproduction evidence and the verified connection context. Obtain
fresh status when the report needs current runtime/health evidence; use
[connection setup](../glyphs/references/connection-session.md) only if unverified
or changed. A connection-only issue needs no font discovery. For a font-specific
reproduction, reuse the intended ID through [document targeting](../glyphs/references/document-targeting.md).
Do not apply an edit merely to collect a report; respect the authorised scope.

For an observed Glyphs crash or unexpected exit, load
[crash recovery](../glyphs/references/crash-recovery.md). It covers uncertain jobs,
conditional continuation and permission for a short diagnostic autosave pause.

Use that status evidence to collect the installed component versions, job identity,
reproduction steps, expected and observed results, and relevant bounded logs.
When native reproduction needs a font, use a disposable copy and verify the
original source remains unchanged. Exclude
authentication tokens and private font data from the report. Prepare the issue
locally; submit to GitHub only when explicitly authorized.

[Documentation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set-v2.mdx).
