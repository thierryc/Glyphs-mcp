# encoding: utf-8

"""Pure helpers for the Glyphs MCP status panel.

This module contains no Glyphs/AppKit imports so it can be unit-tested outside
of Glyphs. The UI layer (glyphs_plugin.py) owns AppKit integration.
"""

from __future__ import division, print_function, unicode_literals


def endpoint_for(port, host="127.0.0.1"):
    """Return the MCP endpoint URL for the given host/port."""
    try:
        port_int = int(port)
    except Exception:
        port_int = None

    if port_int is None or port_int <= 0:
        port_int = 9680

    return "http://{0}:{1}/mcp/".format(host, port_int)


def is_thread_running(thread_obj):
    """Return True if the server thread exists and appears alive."""
    try:
        return bool(thread_obj) and bool(thread_obj.is_alive())
    except Exception:
        return False


def status_text(is_running):
    """Return a short human-readable status string."""
    return "Running" if is_running else "Stopped"

