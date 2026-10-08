# Glyphs MCP Bridge

See the [current eighteen-tool contract](../../content/reference/command-set.mdx)
and [V2 release notes](../../V2-RELEASE.md) for shared behavior and scope.

The bridge is a combined Glyphs plug-in with a small, fixed-height sidebar palette
and an application-wide server settings controller. It exposes an authenticated local
JSON protocol, not MCP. Its responsibilities are limited to:

- status and open-document metadata;
- reads of at most 100 explicit entities;
- target-level preconditions and read-back;
- guarded changes in scheduled chunks with a time budget and batch bound;
- exact native Undo/Redo in each touched glyph's editing history;
- syntax/target preparation and native Python execution (`script.native.v1`);
- verified Save and editor-coordinated saved/historical font reloads.

Completion retains mutation ownership while Undo groups, rounding flags and
temporary target references are released incrementally. Terminal status follows
cleanup, including on cancellation or failure. Individual native calls remain
indivisible; the scheduling budget is not a maximum UI pause. If scheduling
fails, cleanup drains synchronously to restore owned settings and reports failure.

Full-font file copying, hashing, Git and external analysis/export stay in the
sidecar/worker. The bridge performs authorized native document saves and reloads;
ordinary preparation and typed application do not save. Native scripts can have
external effects beyond font recovery. Its palette title includes the bridge version; its single
status row reads “Ready” when connected. A startup error appears in
the status tooltip when one exists. The fixed 30-point content height fits the
single row without unused space below.

**Edit → Glyphs MCP Server…** opens settings even when no font is open. Start
and Stop control both the external MCP server and its Glyphs connection. The
panel shows status, the MCP URL, an automatic-start-at-login setting, and Open
Logs. Process controls run outside Glyphs and never block its main thread.

The native dialog groups server status and connection settings, with an editable
MCP port and Copy URL button. Apply restarts a running sidecar; a stopped server
stays stopped. Invalid, reserved, or occupied ports are rejected before shutdown,
and restart failures restore the previous configuration. Updates preserve the
chosen port. After a port change, update the URL in the MCP client.

Status polls never disable controls or rewrite unchanged content; stale replies
cannot overwrite an action, and typed port values survive refreshes. The footer
credits Thierry Charbonnel and links to GitHub and project sponsorship. It shows
the project version from the plugin manifest and the bridge version separately.

The bridge starts with Glyphs and is shared by every document palette. A manual
Stop remains effective when another document opens. Closing a document does not
stop the shared bridge. Stop refuses shutdown during an active native write;
external preparation is cancelled on shutdown.
The automatic-start setting applies to the external server at the next login.

Dimensions metadata is read only on request for up to four exact masters. Its
closed change type uses native document Undo, exact stored-value preconditions,
readback, and restoration of absent containers. Approval records for overwrites
are validated at the bridge boundary as well as in the sidecar. Other userData
keys are outside this interface.
