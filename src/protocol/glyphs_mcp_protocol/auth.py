"""One shared local secret for the sidecar-to-bridge connection."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def default_token_path() -> Path:
    configured = os.environ.get("GLYPHS_MCP_BRIDGE_TOKEN_FILE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "Library" / "Application Support" / "Glyphs MCP" / "bridge-token"


def load_or_create_token(path: Path | None = None) -> str:
    target = Path(path or default_token_path())
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        value = target.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        value = secrets.token_urlsafe(32)
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return load_or_create_token(target)
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(value + "\n")
    if len(value) < 32:
        raise RuntimeError("Glyphs MCP bridge token is invalid")
    return value
