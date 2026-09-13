# Glyphs MCP Bridge

The bridge is a combined Glyphs plug-in with a small, fixed-height sidebar palette
and an application-wide server settings controller. It exposes an authenticated local
JSON protocol, not MCP. Its responsibilities are limited to:

- status and open-document metadata;
- reads of at most 100 explicit entities;
- target-level preconditions and read-back;
- `set` and `translate` changes in 8–12 ms chunks;
- exact native Undo/Redo in each touched glyph's editing history.

It never copies, serializes, hashes, canonicalizes, or diffs a complete font,
and it never saves. Its palette title includes the bridge version; its single
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
