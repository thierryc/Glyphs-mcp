"""Behavior and safety tests for generic custom-parameter MCP tools."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import math
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


def _resources_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
    )


def _module_path() -> Path:
    return _resources_dir() / "mcp_tools_custom_parameters.py"


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, **kwargs):
        def decorator(function):
            self.tools[function.__name__] = kwargs
            return function

        return decorator


class _Parameter:
    def __init__(self, name, value, active=True):
        self.name = name
        self.value = value
        self.active = active


class _Parameters:
    def __init__(self, records=None):
        self.records = list(records or [])

    def __iter__(self):
        return iter(self.records)

    def __getitem__(self, name):
        matching = [item for item in self.records if item.name == name]
        return matching[-1].value if matching else None

    def __setitem__(self, name, value):
        matching = [item for item in self.records if item.name == name]
        if matching:
            matching[-1].value = value
        else:
            self.records.append(_Parameter(name, value))

    def __delitem__(self, name):
        before = len(self.records)
        self.records[:] = [item for item in self.records if item.name != name]
        if len(self.records) == before:
            raise KeyError(name)


class _FailingParameters(_Parameters):
    def __init__(self, records=None, fail_on_set=None, fail_on_delete=None):
        super().__init__(records)
        self.fail_on_set = set(fail_on_set or [])
        self.fail_on_delete = set(fail_on_delete or [])

    def __setitem__(self, name, value):
        if (name, value) in self.fail_on_set:
            raise RuntimeError("simulated parameter assignment failure")
        super().__setitem__(name, value)

    def __delitem__(self, name):
        if name in self.fail_on_delete:
            raise RuntimeError("simulated parameter deletion failure")
        super().__delitem__(name)


class _Master:
    def __init__(self, master_id, name, records=None):
        self.id = master_id
        self.name = name
        self.customParameters = _Parameters(records)


class _Font:
    def __init__(self, records=None, masters=None):
        self.familyName = "Custom Parameters Test"
        self.filepath = "/tmp/CustomParametersTest.glyphs"
        self.customParameters = _Parameters(records)
        self.masters = list(masters or [])
        self.save_calls = 0

    def save(self):
        self.save_calls += 1


def _resolve_font_by_index(glyphs, font_index):
    fonts = list(getattr(glyphs, "fonts", []) or [])
    try:
        index = int(font_index)
    except (TypeError, ValueError):
        return None, fonts
    if index < 0 or index >= len(fonts):
        return None, fonts
    return fonts[index], fonts


def _font_resolution_error(font_index, fonts=None, ok_key=None):
    payload = {
        "error": "Font index out of range",
        "fontIndex": font_index,
        "availableFontCount": len(fonts or []),
    }
    if ok_key:
        payload[ok_key] = False
    return payload


class McpToolsCustomParametersTests(unittest.TestCase):
    def _load_module(self, font):
        resources = str(_resources_dir())
        if resources not in sys.path:
            sys.path.insert(0, resources)
        glyphs_api = types.SimpleNamespace(fonts=[font], font=font, redraw_calls=0)

        def redraw():
            glyphs_api.redraw_calls += 1

        glyphs_api.redraw = redraw
        fake_mcp = _FakeMCP()
        helpers = types.SimpleNamespace(
            _font_resolution_error=_font_resolution_error,
            _resolve_font_by_index=_resolve_font_by_index,
            _run_on_main_thread=lambda callback: callback(),
            _safe_json=lambda value: json.dumps(value, sort_keys=True),
        )
        modules = {
            "GlyphsApp": types.SimpleNamespace(Glyphs=glyphs_api),
            "mcp_runtime": types.SimpleNamespace(mcp=fake_mcp),
            "mcp_tool_helpers": helpers,
        }
        module_name = "mcp_tools_custom_parameters_under_test"
        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
        return module, font, glyphs_api, fake_mcp

    def test_annotations_distinguish_read_and_write_tools(self):
        module, _font, _glyphs, mcp = self._load_module(_Font())
        self.assertTrue(mcp.tools["get_custom_parameters"]["annotations"]["readOnlyHint"])
        self.assertFalse(mcp.tools["set_custom_parameters"]["annotations"]["readOnlyHint"])
        self.assertTrue(mcp.tools["set_custom_parameters"]["annotations"]["idempotentHint"])
        self.assertIsNotNone(module)

    def test_get_font_parameters_filters_and_reports_duplicates(self):
        font = _Font([
            _Parameter("Example.columns", 24),
            _Parameter("Example.columns", 32),
            _Parameter("Example.rows", 20, active=False),
            _Parameter("Other", "value"),
        ])
        module, _font, _glyphs, _mcp = self._load_module(font)
        payload = json.loads(asyncio.run(module.get_custom_parameters(prefix="Example.")))
        self.assertTrue(payload["ok"])
        self.assertEqual([item["name"] for item in payload["parameters"]], [
            "Example.columns", "Example.columns"
        ])
        self.assertEqual(payload["duplicates"][0]["name"], "Example.columns")

        with_inactive = json.loads(asyncio.run(
            module.get_custom_parameters(prefix="Example.", include_inactive=True)
        ))
        self.assertIn("Example.rows", [item["name"] for item in with_inactive["parameters"]])

    def test_effective_scope_applies_active_master_overrides(self):
        master = _Master("M1", "Regular", [
            _Parameter("Grid.rows", 16),
            _Parameter("Grid.disabled", 99, active=False),
        ])
        font = _Font([
            _Parameter("Grid.columns", 24),
            _Parameter("Grid.rows", 24),
            _Parameter("Grid.disabled", 10),
        ], [master])
        module, _font, _glyphs, _mcp = self._load_module(font)
        payload = json.loads(asyncio.run(
            module.get_custom_parameters(scope="effective", master_id="M1", prefix="Grid.")
        ))
        effective = {item["name"]: item for item in payload["parameters"]}
        self.assertEqual(effective["Grid.columns"]["value"], 24)
        self.assertEqual(effective["Grid.rows"]["value"], 16)
        self.assertEqual(effective["Grid.rows"]["source"], "master")
        self.assertEqual(effective["Grid.disabled"]["value"], 10)

    def test_master_scope_requires_existing_master(self):
        module, _font, _glyphs, _mcp = self._load_module(_Font())
        payload = json.loads(asyncio.run(
            module.get_custom_parameters(scope="master", master_id="missing")
        ))
        self.assertFalse(payload["ok"])
        self.assertIn("not found", payload["error"])

    def test_set_dry_run_previews_without_mutation(self):
        font = _Font([_Parameter("Grid.columns", 24)])
        module, _font, glyphs, _mcp = self._load_module(font)
        payload = json.loads(asyncio.run(module.set_custom_parameters(
            changes={"Grid.columns": 32, "Grid.rows": 20}, dry_run=True
        )))
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["dryRun"])
        self.assertEqual(font.customParameters["Grid.columns"], 24)
        self.assertIsNone(font.customParameters["Grid.rows"])
        self.assertEqual(glyphs.redraw_calls, 0)

    def test_apply_requires_confirm_when_dry_run_is_false(self):
        font = _Font()
        module, _font, glyphs, _mcp = self._load_module(font)
        payload = json.loads(asyncio.run(module.set_custom_parameters(
            changes={"Grid.columns": 24}, dry_run=False, confirm=False
        )))
        self.assertFalse(payload["ok"])
        self.assertIn("confirm", payload["error"])
        self.assertIsNone(font.customParameters["Grid.columns"])
        self.assertEqual(glyphs.redraw_calls, 0)

    def test_confirmed_apply_sets_deletes_redraws_and_never_saves(self):
        font = _Font([
            _Parameter("Grid.columns", 24),
            _Parameter("Grid.remove", True),
        ])
        module, _font, glyphs, _mcp = self._load_module(font)
        payload = json.loads(asyncio.run(module.set_custom_parameters(
            changes={"Grid.columns": 32, "Grid.remove": None, "Grid.rows": 20},
            dry_run=False,
            confirm=True,
        )))
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["applied"])
        self.assertEqual(font.customParameters["Grid.columns"], 32)
        self.assertEqual(font.customParameters["Grid.rows"], 20)
        self.assertIsNone(font.customParameters["Grid.remove"])
        self.assertEqual(glyphs.redraw_calls, 1)
        self.assertEqual(font.save_calls, 0)
        self.assertEqual(
            payload["verifiedParameterNames"],
            ["Grid.columns", "Grid.remove", "Grid.rows"],
        )
        self.assertIsNone(payload["rollback"])

    def test_partial_assignment_failure_rolls_back_the_whole_batch(self):
        font = _Font()
        font.customParameters = _FailingParameters(
            [
                _Parameter("Grid.remove", True, active=False),
                _Parameter("Grid.fail", 10),
            ],
            fail_on_set={("Grid.fail", 20)},
        )
        module, _font, _glyphs, _mcp = self._load_module(font)

        payload = json.loads(asyncio.run(module.set_custom_parameters(
            changes={"Grid.remove": None, "Grid.fail": 20},
            dry_run=False,
            confirm=True,
        )))

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["applied"])
        self.assertEqual(payload["writtenParameterNames"], ["Grid.remove"])
        self.assertTrue(payload["rollback"]["attempted"])
        self.assertTrue(payload["rollback"]["succeeded"])
        self.assertTrue(font.customParameters["Grid.remove"])
        restored = [
            parameter
            for parameter in font.customParameters
            if parameter.name == "Grid.remove"
        ][0]
        self.assertFalse(restored.active)
        self.assertEqual(font.customParameters["Grid.fail"], 10)
        self.assertEqual(font.save_calls, 0)

    def test_redraw_failure_rolls_back_and_verifies_original_state(self):
        font = _Font([_Parameter("Grid.columns", 24)])
        module, _font, glyphs, _mcp = self._load_module(font)
        redraw_calls = []

        def flaky_redraw():
            redraw_calls.append(True)
            if len(redraw_calls) == 1:
                raise RuntimeError("simulated redraw failure")

        glyphs.redraw = flaky_redraw
        payload = json.loads(asyncio.run(module.set_custom_parameters(
            changes={"Grid.columns": 32},
            dry_run=False,
            confirm=True,
        )))

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["applied"])
        self.assertTrue(payload["rollback"]["succeeded"])
        self.assertEqual(font.customParameters["Grid.columns"], 24)
        self.assertEqual(len(redraw_calls), 2)
        self.assertEqual(font.save_calls, 0)

    def test_partial_deletion_failure_rolls_back_earlier_assignments(self):
        font = _Font()
        font.customParameters = _FailingParameters(
            [
                _Parameter("Grid.columns", 24),
                _Parameter("Grid.remove", True),
            ],
            fail_on_delete={"Grid.remove"},
        )
        module, _font, _glyphs, _mcp = self._load_module(font)

        payload = json.loads(asyncio.run(module.set_custom_parameters(
            changes={"Grid.columns": 32, "Grid.remove": None},
            dry_run=False,
            confirm=True,
        )))

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["applied"])
        self.assertEqual(payload["writtenParameterNames"], ["Grid.columns"])
        self.assertTrue(payload["rollback"]["succeeded"])
        self.assertEqual(font.customParameters["Grid.columns"], 24)
        self.assertTrue(font.customParameters["Grid.remove"])
        self.assertEqual(font.save_calls, 0)

    def test_targeted_duplicates_and_non_json_values_are_rejected(self):
        font = _Font([
            _Parameter("Grid.columns", 24),
            _Parameter("Grid.columns", 32),
        ])
        module, _font, _glyphs, _mcp = self._load_module(font)
        duplicate = json.loads(asyncio.run(module.set_custom_parameters(
            changes={"Grid.columns": 20}, dry_run=False, confirm=True
        )))
        self.assertFalse(duplicate["ok"])
        self.assertIn("duplicate", duplicate["error"].lower())
        self.assertEqual(len(font.customParameters.records), 2)

        for value in (object(), math.nan, math.inf):
            invalid = json.loads(asyncio.run(module.set_custom_parameters(
                changes={"Grid.value": value}
            )))
            self.assertFalse(invalid["ok"])


if __name__ == "__main__":
    unittest.main()
