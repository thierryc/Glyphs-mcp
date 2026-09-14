# Source evidence

Native implementation inspected from the current lean source:

- `build/milestone7/desktop/src/bridge/glyphs_mcp_bridge/glyphs_adapter.py`: `_dirty`, `_protect_write`, `_write_exact`, `begin_undo`, `end_undo`.
- `build/milestone7/desktop/src/bridge/glyphs_mcp_bridge/native_undo.py`: eager document fallback group, per-glyph groups, exact inverse registration and registration suppression.
- `build/milestone7/desktop/src/bridge/glyphs_mcp_bridge/kerning.py`: glyph/ fallback manager selection.
- `build/milestone7/desktop/src/bridge/glyphs_mcp_bridge/core.py`: discard performs reverse target writes; it does not globally rewind history.

Installed Glyphs 4.1 (4107) native headers:

- `/Applications/Glyphs 4.app/Contents/Frameworks/GlyphsCore.framework/Versions/A/Headers/GSGlyph.h`: glyph `changeCount`, glyph-owned history.
- Same directory, `GSLayer.h`: layer manager is the containing glyph's manager.
- Same directory, `GSFont.h`: font/document-level history versus individual glyph history.
- Same directory, `GSUndoManager.h`: native change bookkeeping, Undo client protocol, native manager owner.
- `/Applications/Glyphs 4.app/Contents/Frameworks/GlyphsApp.framework/Versions/A/Headers/GSDocument.h`: non-allocating `undoManagerCheck`, autosave state and document lifecycle.
- `/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/System/Library/Frameworks/AppKit.framework/Versions/C/Headers/NSDocument.h`: `isDocumentEdited`, `hasUnautosavedChanges`, change notifications and autosaved versus saved states.

Public primary documentation reviewed:

- [Apple: NSDocument updateChangeCount](https://developer.apple.com/documentation/appkit/nsdocument/updatechangecount(_:)). Default document Undo integration; custom host behavior still requires native evidence.
- [Glyphs forum: Close icon does not show dot on edited file](https://forum.glyphsapp.com/t/close-icon-does-not-show-dot-on-edited-file/32577), January 2025. Different Glyphs 3 UI/autosave context; not a confirmation of this defect.
- [Glyphs forum: Undo has suddenly stopped working properly](https://forum.glyphsapp.com/t/undo-has-suddenly-stopped-working-properly/35637), December 2025. Different Undo symptom with a user-reported plugin involvement; not a diagnosis of this case.

No undocumented compatibility encoding, counter setters, forced-clean marker or new history model was used. The original recorded native UI and public MCP controls remain independent of the later copied-function probes.

To reproduce, use a new output folder and disposable-font directory; update the explicit `O`/`FOLDER` paths in the helpers so existing evidence is never overwritten. Generate the fixture with the installed native CLI and Glyphs 4. Run the setup/read helper through Glyphs' Scripts menu, carry out the test specification with public tools/UI, finish the helper, then run isolated probes separately. Remove only the temporary scripts after their cleanup completes. Do not run either helper against a user's font or change autosaving to obtain a passing indicator.
