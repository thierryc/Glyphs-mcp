"""Lean Glyphs bridge: bounded reads and time-sliced writes only."""

from .companions import CompanionRegistry
from .core import BridgeCore, BridgeError

__all__ = ["BridgeCore", "BridgeError", "CompanionRegistry"]

PROJECT_VERSION = "2.0.0"
