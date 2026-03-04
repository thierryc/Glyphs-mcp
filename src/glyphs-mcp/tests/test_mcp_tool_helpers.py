"""Unit tests for mcp_tool_helpers (pure helpers).

These helpers intentionally avoid importing GlyphsApp so they can be tested in
the normal unit test runner.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


class McpToolHelpersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(_resources_dir()))
        global helpers  # noqa: PLW0603 - simple test import
        import mcp_tool_helpers as helpers  # type: ignore

    def test_round_half_away_from_zero(self) -> None:
        self.assertEqual(helpers._round_half_away_from_zero(0.0), 0)
        self.assertEqual(helpers._round_half_away_from_zero(0.49), 0)
        self.assertEqual(helpers._round_half_away_from_zero(0.5), 1)
        self.assertEqual(helpers._round_half_away_from_zero(1.5), 2)
        self.assertEqual(helpers._round_half_away_from_zero(-0.5), -1)
        self.assertEqual(helpers._round_half_away_from_zero(-1.5), -2)

    def test_sanitize_for_json_nested_objects(self) -> None:
        class Weird:
            def __str__(self) -> str:  # pragma: no cover - exercised via sanitizer
                return "weird"

        payload = {
            "a": 1,
            "b": {1, 2, 3},
            "c": ("x", Weird()),
            "d": {"k": Weird()},
        }

        sanitized = helpers._sanitize_for_json(payload)
        # Must be JSON-serializable without throwing.
        encoded = json.dumps(sanitized)
        self.assertIn('"a"', encoded)
        self.assertIn('"weird"', encoded)

    def test_get_component_automatic_prefers_present_flags(self) -> None:
        class HasAutomatic:
            automatic = True

        class HasAutomaticAlignment:
            automaticAlignment = False

        class HasNeither:
            pass

        self.assertIs(helpers._get_component_automatic(HasAutomatic()), True)
        self.assertIs(helpers._get_component_automatic(HasAutomaticAlignment()), False)
        self.assertIsNone(helpers._get_component_automatic(HasNeither()))

    def test_coerce_numeric_handles_callables_and_errors(self) -> None:
        self.assertEqual(helpers._coerce_numeric("3.5"), 3.5)
        self.assertEqual(helpers._coerce_numeric(2), 2.0)

        class CallableValue:
            def __call__(self):  # pragma: no cover - used by helper
                return "4"

        self.assertEqual(helpers._coerce_numeric(CallableValue()), 4.0)

        class BrokenCallable:
            def __call__(self):  # pragma: no cover - used by helper
                raise RuntimeError("boom")

        self.assertIsNone(helpers._coerce_numeric(BrokenCallable()))

        class NotNumeric:
            def __str__(self) -> str:  # pragma: no cover - helper ignores
                return "nope"

        self.assertIsNone(helpers._coerce_numeric(NotNumeric()))


if __name__ == "__main__":
    unittest.main()

