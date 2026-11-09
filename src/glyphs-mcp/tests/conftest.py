"""Keep native extension imports outside tests that snapshot sys.modules."""
import sys
from pathlib import Path
import pytest

# Every selected subset must resolve this checkout's lean packages, without
# relying on collection of an unrelated test module to mutate sys.path first.
_ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(_ROOT)] + [str(_ROOT / 'src' / name) for name in ('protocol', 'bridge', 'sidecar')]


def pytest_addoption(parser):
    parser.addoption('--performance-gates', action='store_true',
                     help='Enforce latency budgets in addition to functional liveness assertions.')


def pytest_collection_modifyitems(items):
    from scripts.test_selection import INTEGRATION_MODULES
    for item in items:
        if Path(item.path).stem in INTEGRATION_MODULES:
            item.add_marker(pytest.mark.integration)
        if getattr(item.cls, '__name__', None) == 'PythonRuntimeMatrixTests':
            item.add_marker(pytest.mark.dependency)


def pytest_sessionstart(session):
    # Legacy API-double tests restore entire sys.modules snapshots. If PyObjC
    # first loads within such a snapshot, restoration removes its Python module
    # while the extension stays loaded, and subsequent imports refuse a reload.
    # Load it once before those snapshots without opening Glyphs or a document.
    if sys.platform == 'darwin':
        try:
            import objc  # noqa: F401
            import Foundation  # noqa: F401
        except ImportError:
            pass  # Non-native test environments use the existing API doubles.
