# Qualified visible loop and limits

Native observations on 2026-10-11 used Glyphs 4.2 (4201), bundle identifier
`com.GeorgSeifert.Glyphs4`, on macOS. These observations qualify this host/build;
they are not a public API guarantee for other builds or UI automation clients.

The repository evidence is in
[the verification record](../../../reports/macro-iteration-20261011/verification.json).
That report is development evidence, not a runtime dependency of the skill.

| Check | Observed result |
|---|---|
| Native editor | Window → Scripting Window exposed source, resolved file path and Run control through accessibility. |
| Direct file opening | File → Open rejected the workspace `.py` as an unsupported Python script format. |
| Linked workspace source | A new, uniquely named symlink in Glyphs 4/Macros appeared in the sidebar without explicit reload. Selecting it displayed the resolved workspace path and exact print-only source. |
| Execution/capture | Run appended the expected unique marker; embedded console text was readable through accessibility. |
| External edit | Changing the marker in the workspace automatically refreshed the already-selected editor source without reselection or Reload Scripts. |
| Iterated execution | After confirming refreshed source, one rerun appended the revised marker. Prior console history was preserved. |
| Floating console | Opening it after the first run showed no output; it did not mirror the embedded history. |
| Existing traceback | A pre-existing, unrelated FileNotFoundError was readable in embedded console accessibility text. The iteration check did not execute that unrelated script. |

The qualification scripts only printed markers and did not access fonts. They
establish source loading, refresh and output attribution, not correctness or
recovery for mutating macros. An incidental coordinate click enabled Activate
Breakpoints during initial exploration; it was restored to off before execution.
The verified iteration used named accessibility controls.

## Unqualified behavior

- Editing/saving through the symlink inside Glyphs, conflict handling between
  workspace and editor edits, and editor Trash behavior.
- Long or truncated console output, fresh exception generation, output routing
  under different settings, asynchronous output and concurrent runs.
- Mutating macro recovery, native Undo behavior, crash recovery or cancellation.
- Other Glyphs builds, different Python runtimes, and other clients' accessibility
  capture behavior.

Existing native API documentation establishes that `showMacroWindow()` opens
the window and `clearLog()` deletes console contents. Neither loads source,
establishes console routing, or supplies an MCP execution context. Consult the
development skill's pinned offline documentation for unfamiliar APIs.

Use the native scripting contract for MCP jobs. Its pre-run full-font snapshot
and Restore before run do not apply to execution from the Scripting Window.
Automatic refresh must still be checked before every authorized Run.
