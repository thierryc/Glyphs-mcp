### Source Formats

A Glyphs document can be stored in one of three source file formats.
Plug-ins can add support for additional source formats; see Plug-ins.

Pick the source file format when saving with “File” → “Save As…” (Cmd-Shift-S).
Each format is described in the following sections.

#### Glyphs File

The Glyphs File format is the default format in which new Glyphs files are created.
Glyphs files end in the “.glyphs” file suffix.

Pro Tip:

`.glyphs` files are stored as NeXTSTEP-flavor property lists.
They can be opened and edited in a text editor for advanced editing and inspection.

A Glyphs file is _flat_, meaning it is stored as a single file containing all information about the font.

When opening a Glyphs files created in Glyphs 2, Glyphs 3 will keep the file in a Glyphs 2 compatible mode.
This way, the file can still be opened in Glyphs 2 after editing it in Glyphs 3.
However, not all features of Glyphs 3 can be stored in a version 2 file.
In “File” → “Font Info…” → “Other” → “File Saving”, change the “File format version” to “Version 3”.
New Glyphs files are created in the “Version 3” format.
See also File Format Version.

#### Glyphs File Package

The Glyphs File Package format is identical to the Glyphs File format, except it splits parts of the font into separate files and groups those files into a folder with the “.glyphspackage” suffix.
Notably, every glyph is put into its own file.

In Finder, a `.glyphspackage` folder appears as a normal file that can be opened by double-clicking it like any other file.
Inspect its inner contents by Control-clicking or right-clicking the package file in Finder and choosing “Show Package Contents” from the context menu.

A normal Glyphs file requires re-saving the entire file, even if only a single glyph is changed.
Since a package contains a file per glyph, only the files that changed are modified when saving.
While this difference is inconsequential for smaller fonts, the Glyphs package format is recommended for projects with many glyphs (such as CJK fonts).

Splitting every glyph into its own file also helps when managing the document with a version control system (VCS) such as Git.
The frequently changing display strings representing the glyphs of the Edit View tabs are stored in a `UIState.plist` file inside the package.
This makes it easy to ignore user interface changes in the VCS.

#### Unified Font Object

The UFO format is available both as a source file format and as an export format.
When using UFO as a source format, not all features are available in Glyphs.
Activating an unsupported feature will trigger a warning message.

Glyphs supports opening and saving UFO version 2 and version 3 formats.
The version is maintained when opening a UFO file.
New UFO files created using the UFO export are stored in version 3 format.

UFO files end in the “.ufo” suffix.
Like Glyphs packages, they are folders appearing as a normal file in Finder.
Unlike Glyphs files and Glyphs packages, a UFO stores only a single master.

UFO files are compatible with many other font development tools.
Use UFO as a source format when working on a font together with others that use UFO-compatible software.
However, when using UFO for a single-purpose tool (for example, a specialized kerning tool), consider working with a Glyphs file or Glyphs package and exporting to UFO.
The results of the specialized tool can then be imported into the Glyphs file, for instance, by importing metrics.

See Font File Importing Behaviors for file import configuration options.
Configure these options for a specific UFO file in “File” → “Font Info…” → “Other”; see Use Custom Naming and Disable Automatic Alignment.