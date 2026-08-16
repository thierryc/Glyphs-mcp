"""Glyphs MCP 2.0 typed runtime foundation.

Importing the package itself intentionally loads no host or transport adapter.
Callers opt into those boundaries through their explicit submodules.
"""

from .contracts import API_MAJOR, API_VERSION, RESULT_SCHEMA_VERSION
from .versions import SERVER_NAME, SERVER_VERSION

__all__ = [
    "API_MAJOR",
    "API_VERSION",
    "RESULT_SCHEMA_VERSION",
    "SERVER_NAME",
    "SERVER_VERSION",
]
