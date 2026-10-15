# Glyphs MCP agent plugin

This optional repository plugin connects Codex/ChatGPT, Claude Code, Cursor,
and GitHub Copilot CLI to the Glyphs MCP server at
`http://127.0.0.1:9680/mcp/`. Version 2.1.0 bundles the general Glyphs launcher
and ten additional managed skills, including reviewed workspace scripting,
and reusable development, for every host.

Host-native manifests live under `.codex-plugin/`, `.claude-plugin/`,
`.cursor-plugin/`, and `.github/plugin/`. They all reference this package's
single `skills/` directory and `.mcp.json`. Skills inherit the package version;
the coordinated bridge and sidecar product version is 2.1.0. Internal Python
package versions remain 0.1.0; they are separate from release identity.
Glyphs 3 uses the separate pinned 1.11.0 bundle and skills.

Glyphs remains the editor. The native bridge panel displays its status and a
heart button for Welcome & Support. The AI client receives reports and structured
results from twenty data/action tools, plus the optional read-only card-display tool. `accept_job` verifies targets and persists the whole
document; Undo and Redo are grouped per glyph, and discard restores an
unaccepted job with conflict checks.

Glyphs-native commands use the capability-gated `native_action` job family, not
additional tools. The running bridge publishes its filtered closed action
catalog; requests never contain Python, menu names or arbitrary selectors.

The Glyphs application and native Glyphs MCP plug-in must be installed and the
server must be running before the host can connect. Installing this agent
plugin is not required: standalone skills and manual MCP configuration remain
supported. Every supported client receives concise text and structured tool results.

See the repository documentation for the
[plugin UI](../../content/getting-started/codex-chatgpt-plugin-ui.mdx) and
[cross-client skill setup](../../content/getting-started/use-agent-skills.mdx).

The lean Glyphs 4 package exposes twenty data/action tools: get_status, list_documents, create_document, duplicate_document, open_document,
import_document, activate_document, open_edit_tab, close_document,
read_entities, start_job, compare_fonts, get_job, apply_job, accept_job, discard_job,
save_document, start_edit_workflow, get_edit_workflow and respond_edit_workflow.
The additional read-only show_edit_workflow tool opens an optional workflow card.
There is no arbitrary Python execution tool. Install the pinned
Glyphs 3 skills separately when using the 1.11.0 server.

## Conversation interface

Use native questions for unresolved decisions and missing information, grouping
related independent questions. Use ordinary chat when the host has no available
question tool. Routine progress, success and errors use conversation feedback.
Open an optional MCP App card only for useful visual evidence, interactive
inspection, substantial reports, live controls or recovery information, or when
the user requests it. Reuse one useful card across stages. A dedicated visual
glyph comparison or inspector requires a suitable renderer or native Glyphs view;
the workflow card itself supplies lifecycle state, reports and controls.

Choose by actual host capabilities, not client name. Missing cards never block
the text workflow. Shared skills and server descriptions map natural-language
choices to retained actions without asking users for internal identifiers.

Save and continue saves existing work once and resumes the request. Complete
results apply automatically; previews, warnings and required overwrites wait
for review. The resulting edit is not saved without separate authorization.

With Automatic Keep enabled, a visible, connected and freshly reconciled
successful result card can Keep without saving after 30 seconds, ending workflow
recovery. Failed, partial, blocked and uncertain outcomes remain manual. Disable
Automatic Keep before waiting on a native question; silence, Skip and dismissal
apply no choice. Honor “wait for my answer” until the user changes it. Text-only
clients remain manual; no timer authorizes Run, Apply, Save, Undo or Restore.

`compare_fonts` compares explicit compiled TTF files without a live Glyphs
document. It requires the optional managed Diffenator runtime and
`font.compare.diffenator.v1` in `comparisonCapabilities`. Use `get_job` to review
its local report and separately authorize `accept_job` publication to a new
directory. The 2.1.0 source is an unpublished candidate; optional downloads await
hosted assets and supported-platform qualification.
