# MCP Apps conversation workflow — September 22, 2026

Implemented, built, and subsequently installed with user authorization. **The
installation and normal-editor follow-up below supersede the initial pending
installation status. Inline-client qualification remains a separate release
gate; this is not a public-release acceptance record.** Existing Beta 6/Dimensions changes
were preserved and included in the candidate; no commit or publication occurred.

## Delivered

- Saved the accepted plan in `V2-CONVERSATION-WORKFLOW-PLAN.md`.
- Added the three workflow tools and `edit.workflow.v1`, retaining the original
  nine signatures and underlying source, target, save, Undo and recovery services.
- Added a persistent coordinator with request retention, revision/action tokens,
  idempotency, one pending follow-up per document, background continuation, and
  interrupted-operation reconciliation without replaying saves or mutations.
- Save and continue saves existing work once and resumes the retained request.
  Complete ordinary results apply automatically and remain unsaved. Explicit
  previews and report warnings/incomplete targets hold for review; Dimensions
  keeps its exact overwrite-approval guard.
- Added one self-contained standard MCP App: initialization, tool calls, context
  updates, theme variables, visible focus, live status, inline Save As, progress,
  report samples, guarded actions, teardown and visible/active-only polling.
  Warning/incomplete reports direct users to conversation review before applying.
- Every workflow response includes human-readable text and structured state.
  Skills and tool descriptions explain natural-language actions, including
  “save and continue,” without asking users for tool names, IDs or JSON.
- Fixed two pinned FastMCP 2.12 compatibility gaps: parameterized MCP Apps MIME
  forwarding and resource-read CSP metadata. HTTP and the local stdio proxy
  preserve tool UI metadata, the resource, structured results and useful text.
- Updated shared plugin manifests, mirrored skills, tutorial, tool reference,
  packaging inventories and catalog checks. No separate client UI was added.

## Verified

| Check | Result |
|---|---|
| Full Python suite | **2,148 passed, 2 skipped**, 80.19 s; see `python-tests.md` |
| Final focused workflow/UI/save/build tests | **56 passed**, including resource CSP forwarding and report-review controls |
| Native installer XCTest suite | **203 passed**, zero failures |
| Deterministic installer payload | Two independently assembled payload directories compare identically |
| Private arm64 and x86_64 runtime HTTP + stdio | Twelve-tool catalogs, App resource/MIME/CSP, structured and text results; no downloads |
| Python wheel | Bundled `edit_workflow_v1.html` is included |
| Documentation site | Production build passed |
| Skill synchronization and lean package gate | Eleven mirrored skills, twelve public tools; passed |
| Local desktop app | Fresh DerivedData build, compiled assets and build receipt verified |
| Patch whitespace | `git diff --check` passed |

The tests cover clean/dirty/pathless fonts; prerequisite and final saves;
Save As collision/retry; manual Save As; preview, no-change and complete results;
full-report warnings/skips beyond the public sample; pending previous work;
stale preparation; cancellation; duplicate and simultaneous actions; restart;
uncertain save reconciliation; closed documents; final Save As identity; and
discard conflicts preserving subsequent edits. The unchanged native service
regressions also cover the mutation families, recovery and exact history.

The actual bundled JavaScript ran in a deterministic standard-host fixture,
including initialization failure, missing tool capability, permission failure,
no automatic mutation retry, older revisions, teardown and overwrite consent.
A local browser fixture was visually inspected in light/dark themes and with
Save As expanded. This proves browser behavior, **not inline support in a client**.

## Initial client inventory, before reconnecting

| Client installed here | Evidence | Inline qualification of this candidate | Text qualification |
|---|---|---|---|
| Claude Desktop 1.34493.0 | Existing local stdio connection; standard support documented | Pending | Candidate text envelope/flow verified through the equivalent stdio transport; actual client interaction pending |
| Cursor desktop 3.14.7 | Standard MCP Apps support explicitly documented | Pending | Server text workflow verified; actual client interaction pending |
| Codex desktop host 26.915.31945, build 9922 (`com.openai.codex`) | Local application contains the standard MCP Apps renderer, UI resource discovery, initialization and server-tool bridge | Pending; runtime gates/rendering not inferred from source markers | Installed Beta 5 status call verified in this task; candidate conversation interaction pending |
| Claude Code / Codex CLI / other clients | Capability-driven App with complete text contract | No product-name assumptions | Protocol-level text flow verified without installed skills; individual client sessions pending |

Codex local evidence includes `mcp-tool-item-content-ec46a9b81cc5.js`,
`mcp-extension-view-frame-48d8f7deda8f.js`, and `app-initial-a498f911edeb.js`
inside `/Applications/ChatGPT.app/Contents/Resources/app.asar`. These contain
standard resource/MIME discovery, `ui/initialize`, tool-result notifications,
and `serverTools`. Feature gates are present; code presence is not an inline
rendering test and is not inferred from ChatGPT's published support.

References: [MCP Apps overview](https://apps.extensions.modelcontextprotocol.io/api/documents/overview.html),
[Claude local-host quickstart](https://apps.extensions.modelcontextprotocol.io/api/documents/quickstart.html),
[Cursor MCP documentation](https://cursor.com/docs/mcp), and
[OpenAI capability guidance](https://developers.openai.com/plugins/build/chatgpt-ui).

## Native probes and remaining gates

The isolated Glyphs CLI probes ran against Glyphs **4.1 (4107)**. They did not
establish native acceptance. The standalone document save raised
`NSInternalInconsistencyException: dataOfType:error: is a subclass responsibility
but has not been overridden`. Separate history probes encountered open/invalid
Undo groups in the synthetic document/glyph event lifecycle. The coordinator
reported uncertain save execution or native write failure; it did not treat
these probes as success or bypass the existing guards. See the two probe JSON
files and `scripts/qualify_edit_workflow_native.py`. These results must not be
extrapolated to the normal editor's save/history behavior.

At the initial implementation gate, the running system was **Beta 5, build 47**, with nine tools.
Its sidecar and bridge were reachable; the normal editor was not relaunched,
and no user font was saved, edited or closed by this implementation task.
Installed plugins are not linked to this worktree's candidate payload.

The initial remaining gates were:

1. Install the verified local candidate; preserve current settings and existing
   job records. Relaunch Glyphs only after the user's open work is saved. Verify
   source/built/installed identities and the actual loaded bridge/sidecar status.
2. In Claude Desktop, then Cursor, then this Codex host, use a fresh disposable
   font. Verify one Save and continue reaches ordinary application without a
   second user message and leaves the result unsaved. Record exact host versions,
   inline screenshot/result and the native save receipt independently.
3. Verify preview/apply/discard and separate final Save/Save As in the normal
   editor, including native glyph Undo/Redo. Recheck a stale card and closed card.
4. Repeat actions through ordinary text with no skills and with UI unavailable;
   verify failed initialization/tool capability leaves the text route usable.
5. Record verified inline and verified text results separately. Only introduce
   a supported host-specific choice adapter if standard support is actually
   unavailable. No such unavailability has been established here.

Candidate: `dist/local/Glyphs MCP.app`; receipt: `dist/local/build-receipt.json`.
The record's `candidate-identity.json`, `build-receipt.json`, and
`private-runtimes.json` identify what was built/tested. Installation and live
qualification were remaining release gates at that initial record.

## Authorized installation and normal-editor follow-up

The user explicitly requested installation, relaunch, and font saving. Saved
Dactylotype with Glyphs' native Save and verified `dirty: false` before quitting.
Installed the verified candidate using the packaged transactional installer,
preserving job records, selected companions, settings and client configuration.
Backed up the previous desktop app, installed `dist/local/Glyphs MCP.app`, and
relaunched both Glyphs 4 and Glyphs MCP. The manager shows Beta 6, build 48, Ready.

Fresh status through this Codex task verifies both loaded hashes against
`candidate-identity.json`: sidecar `fd468ae49ee2…` and bridge `c288fa8ec5bf…`,
all twelve tools, `edit.workflow.v1`, and Glyphs 4.1 (4107). The installed desktop
bundle separately passes `verify_desktop_app.py` against the build receipt.
Dactylotype reopened clean, with the identical source hash after relaunch.
See `desktop-install.json`, `components-install.json`, `loaded-after-install.json`,
and `user-font-save.json`; recoverable application/component backups are recorded.

A normal-editor disposable font now verifies the native workflow that the earlier
headless fixture could not establish:

- Started dirty at A width 610. One Save and continue saved 610, ran the real
  worker, and applied +8 to 618 without another model/user turn. Disk retained
  610 and the editor remained dirty; the outline hash stayed identical.
- Duplicate start returned the same workflow; repeating its consumed Save and
  continue token produced no duplicate delta. See `live-save-continue.json`.
- Native glyph Undo restored 610; Redo restored 618. Guarded workflow discard
  restored 610 without writing the source file.
- A separate preview kept 610 live until Apply. Applying +9 produced 619, and
  separately selecting final Save As wrote a new destination with 619, verified
  clean by native save evidence and source hash. The old source stayed unchanged.
  Repeating final Save As returned the existing result. See `live-review-save.json`.
- Installed HTTP discovery/read verifies the App MIME, tool UI metadata,
  resource CSP, and useful text plus structured errors. See `installed-protocol.json`.

These checks establish installed native behavior and protocol support. They do
not by themselves establish inline rendering or user interaction in Claude,
Cursor, or Codex.

## Claude Desktop inline follow-up

After restarting Claude Desktop and its local stdio proxy, the actual running
client is **2.2553.13** (the earlier inventory above predates that restart).
Its existing qualification conversation renders the standard App resource in
Claude's MCP Apps iframe, including scope, distinguishing path, saved state,
and text beside the card. The old nine-tool catalog disappeared after restart.

On the disposable font, Claude started an A width +1 request from ordinary
conversation scope. The card displayed Save and continue, Save As, manual Save,
and Cancel. Clicking **Save and continue** once directly invoked the shared
workflow, displayed Preparing, then **Applied in Glyphs · Not saved**, with
620 → 621. No additional Claude/model turn was needed. An independent native
read confirmed 621 live, 620 on disk, and a dirty document. A separate final
Save font action was subsequently observed and returned a verified receipt.
See `claude-inline.json` and `client-versions.json`.

This establishes real standard inline rendering, card tool calls, status
updates, and concurrent human-readable text for Claude Desktop through the
existing local connection. It does not claim every card action was individually
exercised in that client. Terminal cards currently show an empty choice suffix
(“You can also reply in the conversation: .”); this is a cosmetic follow-up,
not an execution or text-contract failure.

## Cursor and Codex follow-up

Cursor was restarted to clear its earlier nine-tool catalog. The running
**Cursor 3.21.18** then successfully called `get_edit_workflow` through the
existing `user-glyphs-mcp-server` connection. Expanding the tool activity and
its result revealed the shared **Glyphs edit workflow** in a standard MCP App
webview, showing the saved disposable result and recovery disclosure. The
original text response remained visible beside it. No Cursor-specific UI or
configuration change was required. This verifies real inline rendering and
text lookup; mutation buttons were exercised in Claude, not Cursor.

One Cursor automation paste failed to enter the requested text and the client
received an unrelated arithmetic image. The actual qualification request was
subsequently typed directly, inspected before sending, and kept read-only.
That image interaction is not qualification evidence.

The current **Codex 26.915.31945 (9922)** task successfully reads the installed
Beta 6 status and native font state, but its model-visible connector catalog
still contains the nine tools loaded before installation. There is no callable
workflow tool in this active task's catalog, so inline rendering is **pending
a connection/task refresh**, not classified as unsupported. The actual host's
standard renderer source evidence remains recorded above. No host-specific
alternative was added on the basis of this stale catalog.

The disposable font was saved and closed after testing. Dactylotype is again
the sole open font, clean; its hash still matches the save before installation.
Remaining release checks include the refreshed Codex inline session, broader
per-client action scenarios, and text-only human conversation actions beyond
the tested protocol contract and client text lookups. These limits do not block
the user's requested local installation and relaunch, which are complete.

## Save UI retest before Beta 6

The user requested another actual-client save test. See
[the retest record](retest/report.md) and its native/source evidence. Claude
and Cursor card saves passed, including prerequisite/final-save separation.
The retest found a failing Claude natural-language save fallback and Cursor
stale-state/permission-timeout presentation. Codex's new inline workflow still
cannot be verified from this task. **Hold the release** until those findings
and the refreshed Codex check are resolved; this supersedes any interpretation
of earlier protocol/card passes as complete client acceptance.
