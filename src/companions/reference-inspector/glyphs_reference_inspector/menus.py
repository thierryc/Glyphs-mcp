"""Manual reference selection without a dependency on MCP."""

from pathlib import Path

from AppKit import NSAlert, NSMenu, NSMenuItem, NSOpenPanel, NSTextField, NSView, NSMakeRect
from GlyphsApp import EDIT_MENU, Glyphs


COMMANDS = (("last_saved", "Last Saved", "useLastSaved_"),
            ("file", "Font File…", "chooseFile_"),
            ("local_git", "Local Git…", "chooseLocalGit_"),
            ("github", "Public GitHub…", "chooseGitHub_"),
            ("refresh", "Refresh Reference", "refreshReference_"))


def install_menu(owner):
    root = NSMenuItem.new(); root.setTitle_("Comparison Reference")
    menu = NSMenu.alloc().initWithTitle_("Comparison Reference")
    menu.setAutoenablesItems_(False)
    menu.setDelegate_(owner)
    for kind, title, action in COMMANDS:
        item = NSMenuItem.new(); item.setTitle_(title); item.setTarget_(owner); item.setAction_(getattr(owner, action))
        item.setRepresentedObject_(kind)
        menu.addItem_(item)
    root.setSubmenu_(menu)
    Glyphs.menu[EDIT_MENU].append(root)
    return root


def _short(value, limit):
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[:limit-13] + "…" + text[-12:]


def refresh_menu(menu, source, spec, *, has_font):
    """Read only active-font preferences; never load a font or resolve Git here."""
    spec = spec if isinstance(spec, dict) else {}
    selected = spec.get("kind", "last_saved") if source else None
    unavailable = "Save this font before choosing a comparison reference." if has_font else "Open a font to choose a comparison reference."
    for item, (kind, title, _) in zip(menu.itemArray(), COMMANDS):
        checked = bool(source and kind == selected and kind != "refresh")
        tooltip = unavailable if not source else None
        if checked:
            path = str(source if kind == "last_saved" else spec.get("source") or "")
            if kind in ("last_saved", "file"):
                detail = _short(Path(path).name, 44)
                tooltip = "File: " + str(Path(path).expanduser())
            else:
                revision = str(spec.get("revision") or "HEAD")
                font_path = str(spec.get("fontPath") or "")
                detail = _short(Path(font_path or source).name, 34) + " @ " + _short(revision, 26)
                repository = path if kind == "github" else str(Path(path or source).expanduser() if path else Path(source).parent)
                tooltip = "Repository: {}\nRevision: {}\nFont path: {}".format(repository, revision, font_path or "Automatic from current font: " + source)
            title = title.rstrip("…") + " — " + detail + ("…" if title.endswith("…") else "")
        item.setTitle_(title)
        item.setState_(1 if checked else 0)
        item.setToolTip_(tooltip)
        item.setEnabled_(bool(source))


def choose_file():
    panel = NSOpenPanel.openPanel()
    panel.setTitle_("Choose Comparison Reference")
    panel.setAllowedFileTypes_(["glyphs", "glyphspackage"])
    panel.setCanChooseDirectories_(False)
    panel.setAllowsMultipleSelection_(False)
    if panel.runModal() == 1:
        return {"kind": "file", "source": str(panel.URL().path())}
    return None


def choose_git(kind, previous):
    alert = NSAlert.alloc().init()
    alert.setMessageText_("Local Git Reference" if kind == "local_git" else "Public GitHub Reference")
    alert.setInformativeText_("Choose a saved font at a branch, tag, or commit. The reference is loaded in the background.")
    alert.addButtonWithTitle_("Compare"); alert.addButtonWithTitle_("Cancel")
    view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 440, 150))
    fields = {}
    for index, (key, title, placeholder) in enumerate([
            ("source", "Repository", "/path/to/repository" if kind == "local_git" else "https://github.com/owner/repository"),
            ("revision", "Revision", "HEAD"), ("fontPath", "Font path in repository", "sources/Font.glyphspackage")]):
        y = 112 - index * 48
        label = NSTextField.labelWithString_(title); label.setFrame_(NSMakeRect(0, y+20, 430, 18))
        field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, y-2, 430, 24))
        field.setPlaceholderString_(placeholder)
        field.setStringValue_(str(previous.get(key) or ("HEAD" if key == "revision" else "")))
        view.addSubview_(label); view.addSubview_(field); fields[key] = field
    alert.setAccessoryView_(view)
    if alert.runModal() == 1000:
        return {"kind": kind, **{key: str(field.stringValue()).strip() for key, field in fields.items()}}
    return None
