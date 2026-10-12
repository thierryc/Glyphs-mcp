"""Keep native extension imports outside tests that snapshot sys.modules."""
import sys


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
