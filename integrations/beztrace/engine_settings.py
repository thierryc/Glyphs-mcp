# Copyright 2026 Glyphs MCP contributors
# SPDX-License-Identifier: Apache-2.0
"""Shared persistent engine contract for the separately released companion.

This module belongs in beztrace_companion in a qualified Beztrace release.
It is not a bridge endpoint and never mutates a font.
"""
import json
import os
from pathlib import Path
import tempfile


def settings_path(home=None):
    return Path(home or Path.home()) / 'Library/Application Support/beztrace/engine-settings-v1.json'


def load(home=None):
    path = settings_path(home)
    if path.is_symlink(): raise ValueError('Engine settings must not be a symbolic link')
    if not path.exists(): return {'schemaVersion': 1}
    if path.stat().st_size > 16384: raise ValueError('Engine settings exceed 16 KiB')
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get('schemaVersion') != 1:
        raise ValueError('Unsupported Beztrace engine settings')
    return value


def selected_engine(default, home=None):
    value = load(home)
    # A missing explicit override remains an actionable error, never a silent
    # switch to a different engine. The engine transport validates the executable.
    for key in ('userEngine', 'managedEngine'):
        path = value.get(key)
        if path is not None:
            if not isinstance(path, str) or not Path(path).is_absolute() or '\0' in path:
                raise ValueError('Engine path must be absolute')
            return path
    return default


def save_user_engine(executable, home=None):
    if not isinstance(executable, str) or not Path(executable).is_absolute() or not os.access(executable, os.X_OK):
        raise ValueError('Choose an existing executable')
    path = settings_path(home)
    for parent in path.parents:
        if parent.is_symlink() and str(parent) not in ('/tmp', '/var'):
            raise ValueError('Engine settings parent is a symbolic link')
    path.parent.mkdir(parents=True, exist_ok=True)
    value = load(home)
    value['userEngine'] = executable
    descriptor, temporary = tempfile.mkstemp(prefix='.engine-settings-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
