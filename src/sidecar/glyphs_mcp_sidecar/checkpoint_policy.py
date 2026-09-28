"""One opt-in project configuration shared with the desktop app."""
import json
from pathlib import Path

CONFIG = '.glyphs-mcp.json'
CAPABILITY = 'font.checkpoints.v1'


def policy_for(font):
    from .checkpoint_git import CheckpointError
    if not font:
        return None
    path = Path(font).absolute()
    for parent in path.parents:
        config = parent / CONFIG
        if config.exists() or config.is_symlink():
            if config.is_symlink() or not config.is_file() or config.stat().st_size > 16384:
                raise CheckpointError('checkpoint_policy_invalid', 'The project checkpoint configuration is unsafe or too large.')
            try:
                value = json.loads(config.read_text())
                setting = value['gitCheckpoints']['enabled']
                if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1 or type(setting) is not bool:
                    raise ValueError('unsupported schema')
            except (ValueError, KeyError, TypeError) as exc:
                raise CheckpointError('checkpoint_policy_invalid', 'The project checkpoint configuration is invalid.') from exc
            return dict(project=str(parent.resolve()), configuration=str(config), enabled=True) if setting else None
        # Do not inherit a containing project's policy across a repository boundary.
        if (parent / '.git').exists():
            return None
    return None
