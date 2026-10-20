"""The actual desktop runner must launch and time out under a one-worker pool."""
import importlib.util
from pathlib import Path
import shutil
import sys

import pytest


@pytest.mark.skipif(sys.platform != 'darwin' or not shutil.which('xcrun'), reason='Native Swift subprocess qualification')
def test_process_capture_does_not_starve_launch_deadline_or_cancellation():
    root = Path(__file__).resolve().parents[3]
    path = root / 'scripts/qualify_process_runner_pool.py'
    spec = importlib.util.spec_from_file_location('qualify_process_runner_pool', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.qualify()
    assert result['passed'], result
    assert len(result['cases']) == 10
