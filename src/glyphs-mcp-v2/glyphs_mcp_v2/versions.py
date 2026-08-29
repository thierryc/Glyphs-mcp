"""Version constants for the unreleased v2 development runtime."""

SERVER_NAME = "Glyphs MCP Server"
SERVER_VERSION = "2.0.0"


def _display_build_number(value):
    """Normalize Glyphs' float build API for compact UI presentation."""

    try:
        resolved = value() if callable(value) else value
    except Exception:
        return ""
    text = str(resolved or "").strip()
    if not text:
        return ""
    try:
        number = float(text)
    except (TypeError, ValueError, OverflowError):
        return text
    if number.is_integer():
        return str(int(number))
    return text


def palette_display_name(glyphs_build_number=None):
    """Return the native palette title with runtime version and host build."""

    title = "Glyphs MCP · {}".format(SERVER_VERSION)
    build = _display_build_number(glyphs_build_number)
    return "{} ({})".format(title, build) if build else title


__all__ = ["SERVER_NAME", "SERVER_VERSION", "palette_display_name"]
