## Git checkpoints for font saves

This project uses local Git checkpoints for authorized MCP font edits and saves.

Before editing, ensure the verified saved baseline is represented by a
checkpoint. Reuse an existing matching checkpoint when possible.

After an authorized MCP save completes and is verified, create a local
checkpoint containing the intended font and its action record. Include the
intended change, affected scope and actual verification evidence.

Preserve unrelated files and staged changes. Do not create empty commits,
initialize another repository or push automatically.

If committing fails after saving, report “Font saved; checkpoint failed.”
Reconcile or retry the checkpoint without repeating the edit or Save.

Keep without saving creates no result checkpoint. This policy authorizes local
checkpoints, not additional font saves.

Explain whole-font restoration coverage before restoring a historical version.
Never reset the whole repository or overwrite files behind an open Glyphs font.
