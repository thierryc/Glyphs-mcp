"""Offline server branding and request-scoped activity metadata."""
import asyncio
import base64
from functools import lru_cache
from pathlib import Path

FEEDBACK_DELAY_SECONDS = 1.0
REPORT_TIMEOUT_SECONDS = 0.5


@lru_cache(maxsize=1)
def icon_uri():
    image = Path(__file__).with_name('assets').joinpath('icon.png').read_bytes()
    return 'data:image/png;base64,' + base64.b64encode(image).decode('ascii')


def configure_identity(server):
    # FastMCP 2.12 does not expose icons in its constructor. The locked runtime's
    # MCP SDK does; older developer SDKs can still use the plugin's artwork.
    from mcp import types
    native = server._mcp_server
    if hasattr(types, 'Icon') and hasattr(native, 'icons'):
        native.icons = [types.Icon(src=icon_uri(), mimeType='image/png', sizes=['1024x1024'])]
        native.website_url = 'https://ap.cx/gmcp'


def invocation_meta(base, invoking, invoked):
    return {**base, 'openai/toolInvocation/invoking': invoking,
            'openai/toolInvocation/invoked': invoked}


async def workflow_call(callback, context, message):
    """Report only this request's lifetime; never retain its context for a job."""
    async def report(value, text):
        if context is not None:
            try:
                await asyncio.wait_for(context.report_progress(value, message=text), timeout=REPORT_TIMEOUT_SECONDS)
            except Exception:
                # Presentation failure must not fail or replay an operation.
                pass

    task = asyncio.create_task(asyncio.to_thread(callback))
    try:
        done, _ = await asyncio.wait({task}, timeout=FEEDBACK_DELAY_SECONDS)
        reporting = not done and context is not None
        if reporting:
            await report(0, message)
        result = await task
        if reporting:
            payload = result.structured_content or {}
            if payload.get('ok'):
                progress = (payload.get('data') or {}).get('progress') or {}
                final = progress.get('label', 'Glyphs workflow status checked')
            else:
                final = 'Glyphs request needs attention'
            await report(1, final)
        return result
    finally:
        # Cancelling this await never cancels/replays the native operation or
        # leaves a telemetry task retaining the ended request's context.
        if not task.done():
            task.cancel()
