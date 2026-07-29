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


def server_lifecycle_state(server_obj, thread_obj, stopping=False):
    """Classify the embedded server without equating a live thread with readiness."""
    if not is_thread_running(thread_obj):
        return "stopped"
    if stopping:
        return "stopping"
    try:
        if bool(server_obj) and bool(getattr(server_obj, "started", False)):
            return "running"
    except Exception:
        pass
    return "starting"


def server_exit_kind(server_started=False, was_ready=False, stop_requested=False):
    """Classify why the server thread exited."""
    if stop_requested:
        return "intentional"
    if bool(server_started) or bool(was_ready):
        return "unexpected"
    return "startup_failed"


def should_emit_start_success(is_ready, was_ready):
    """Return True only for the first confirmed transition to ready."""
    return bool(is_ready) and not bool(was_ready)


def should_show_start_failure_alert(manual_start, exit_kind):
    """Manual startup failures are modal; automatic failures stay non-modal."""
    return bool(manual_start) and exit_kind == "startup_failed"


def status_text(is_running):
    """Return a short human-readable status string."""
    return "running" if is_running else "stopped"
