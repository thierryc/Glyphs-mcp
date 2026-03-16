"""Regression tests for execute_code helpers."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import sys
import traceback
import types
import unittest
from pathlib import Path
from unittest import mock


def _module_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "Glyphs MCP.glyphsPlugin"
        / "Contents"
        / "Resources"
        / "code_execution.py"
    )


class _FakeMCP:
    def tool(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator


class _FakeObjCMeta(type):
    registry: dict[str, type] = {}

    def __new__(mcls, name, bases, namespace):
        if name in mcls.registry:
            raise RuntimeError(f"{name} is overriding existing Objective-C class")
        cls = super().__new__(mcls, name, bases, namespace)
        mcls.registry[name] = cls
        return cls


class _FakeNSObject(metaclass=_FakeObjCMeta):
    @classmethod
    def alloc(cls):
        return cls()

    def init(self):
        return self

    def performSelectorOnMainThread_withObject_waitUntilDone_(self, selector, obj, _wait):
        getattr(self, selector.replace(":", "_"))(obj)


class _FakeObjCModule:
    @staticmethod
    def super(cls, obj):
        return super(cls, obj)

    @staticmethod
    def lookUpClass(name):
        if name not in _FakeObjCMeta.registry:
            raise KeyError(name)
        return _FakeObjCMeta.registry[name]


class CodeExecutionTests(unittest.TestCase):
    def _load_module(self, module_name: str = "glyphs_mcp_test_code_execution"):
        fake_layer = types.SimpleNamespace(name="Regular")
        fake_master = types.SimpleNamespace(id="m1")
        fake_glyph = types.SimpleNamespace(name="A", layers={"m1": fake_layer})
        fake_font = types.SimpleNamespace(
            familyName="Unit Test Sans",
            glyphs={"A": fake_glyph},
            selectedFontMaster=fake_master,
            masters=[fake_master],
        )
        glyphs_app = types.ModuleType("GlyphsApp")
        glyphs_app.GSGlyph = type("GSGlyph", (), {})
        glyphs_app.GSLayer = type("GSLayer", (), {})
        glyphs_app.GSPath = type("GSPath", (), {})
        glyphs_app.GSNode = type("GSNode", (), {})
        glyphs_app.GSComponent = type("GSComponent", (), {})
        glyphs_app.GSAnchor = type("GSAnchor", (), {})

        class FakeScriptingHandler:
            def __init__(self, glyphs_module):
                self.calls = []
                self.glyphs_module = glyphs_module

            def runMacroString_stdOut_(self, code, collector):
                self.calls.append(code)

                def fake_print(*args, **kwargs):
                    sep = kwargs.get("sep", " ")
                    end = kwargs.get("end", "\n")
                    text = sep.join(str(arg) for arg in args) + end
                    collector.setWrite_(text)

                namespace = {
                    "__builtins__": __builtins__,
                    "__name__": "__main__",
                    "print": fake_print,
                }
                try:
                    with mock.patch.dict(sys.modules, {"GlyphsApp": self.glyphs_module}):
                        exec(code, namespace, namespace)
                except Exception:
                    collector.setWriteError_(traceback.format_exc())

        fake_handler = FakeScriptingHandler(glyphs_app)
        glyphs_app.Glyphs = types.SimpleNamespace(
            fonts=[fake_font],
            scriptingHandler=lambda: fake_handler,
        )

        spec = importlib.util.spec_from_file_location(module_name, _module_path())
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(
            sys.modules,
            {
                "GlyphsApp": glyphs_app,
                "mcp_tools": types.SimpleNamespace(mcp=_FakeMCP()),
            },
        ):
            sys.modules.pop(module_name, None)
            assert spec.loader is not None
            spec.loader.exec_module(module)
        return module, fake_handler

    def _configure_fake_objc(self, module, *, reset_registry: bool = False) -> None:
        if reset_registry:
            _FakeObjCMeta.registry = {}
        module.objc = _FakeObjCModule()
        module.NSObject = _FakeNSObject
        module._OBJC_OUTPUT_COLLECTOR_CLASS = None
        module._OBJC_SCRIPT_RUNNER_CLASS = None

    def test_execute_code_terminal_expression_runs_once(self) -> None:
        module, handler = self._load_module()
        out = asyncio.run(module.execute_code("x = []\n(x.append(1), len(x))[1]"))
        payload = json.loads(out)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["result"], "1")
        self.assertEqual(len(handler.calls), 1)

    def test_execute_code_with_context_terminal_expression_runs_once(self) -> None:
        module, handler = self._load_module()
        out = asyncio.run(module.execute_code_with_context("x = []\n(x.append(glyph.name), len(x))[1]", glyph_name="A"))
        payload = json.loads(out)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["result"], "1")
        self.assertEqual(payload["context"]["font"], "Unit Test Sans")
        self.assertEqual(payload["context"]["glyph"], "A")
        self.assertEqual(payload["context"]["layer"], "Regular")
        self.assertEqual(len(handler.calls), 1)

    def test_execute_code_runner_captures_output_and_result(self) -> None:
        module, _handler = self._load_module()
        out = asyncio.run(module.execute_code("print('hello from glyphs')\n41 + 1"))
        payload = json.loads(out)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["output"], "hello from glyphs\n")
        self.assertEqual(payload["result"], "42")

    def test_execute_code_runner_reports_errors(self) -> None:
        module, _handler = self._load_module()
        out = asyncio.run(module.execute_code("raise RuntimeError('boom')"))
        payload = json.loads(out)
        self.assertFalse(payload["success"])
        self.assertIn("RuntimeError: boom", payload["error"])

    def test_execute_code_signatures_no_longer_expose_timeout(self) -> None:
        module, _handler = self._load_module()
        self.assertNotIn("timeout", inspect.signature(module.execute_code).parameters)
        self.assertNotIn("timeout", inspect.signature(module.execute_code_with_context).parameters)

    def test_execute_code_runner_reuses_objc_bridge_classes(self) -> None:
        module, handler = self._load_module()
        self._configure_fake_objc(module, reset_registry=True)

        first = json.loads(asyncio.run(module.execute_code("40 + 2")))
        second = json.loads(asyncio.run(module.execute_code("41 + 1")))

        self.assertTrue(first["success"])
        self.assertTrue(second["success"])
        self.assertEqual(first["result"], "42")
        self.assertEqual(second["result"], "42")
        self.assertEqual(len(handler.calls), 2)
        self.assertEqual(
            sorted(_FakeObjCMeta.registry),
            [module._OBJC_OUTPUT_COLLECTOR_CLASS_NAME, module._OBJC_SCRIPT_RUNNER_CLASS_NAME],
        )

    def test_execute_code_runner_reuses_objc_bridge_classes_across_module_reload(self) -> None:
        first_module, _first_handler = self._load_module("glyphs_mcp_test_code_execution_first")
        self._configure_fake_objc(first_module, reset_registry=True)
        first_output_class = first_module._get_output_collector_class()
        first_runner_class = first_module._get_script_runner_class()

        second_module, second_handler = self._load_module("glyphs_mcp_test_code_execution_second")
        self._configure_fake_objc(second_module)
        second_output_class = second_module._get_output_collector_class()
        second_runner_class = second_module._get_script_runner_class()
        payload = json.loads(asyncio.run(second_module.execute_code("40 + 2")))

        self.assertTrue(payload["success"])
        self.assertEqual(payload["result"], "42")
        self.assertIs(first_output_class, second_output_class)
        self.assertIs(first_runner_class, second_runner_class)
        self.assertEqual(len(second_handler.calls), 1)

    def test_execute_code_runner_ignores_legacy_fixed_name_helpers(self) -> None:
        module, handler = self._load_module()
        self._configure_fake_objc(module, reset_registry=True)

        legacy_output_class = type("GlyphsMCPOutputCollector", (_FakeNSObject,), {"__module__": __name__})
        legacy_runner_class = type("GlyphsMCPScriptRunner", (_FakeNSObject,), {"__module__": __name__})
        payload = json.loads(asyncio.run(module.execute_code("40 + 2")))
        output_class = module._get_output_collector_class()
        runner_class = module._get_script_runner_class()

        self.assertTrue(payload["success"])
        self.assertEqual(payload["result"], "42")
        self.assertEqual(len(handler.calls), 1)
        self.assertIsNot(output_class, legacy_output_class)
        self.assertIsNot(runner_class, legacy_runner_class)
        self.assertCountEqual(
            _FakeObjCMeta.registry,
            [
                "GlyphsMCPOutputCollector",
                "GlyphsMCPScriptRunner",
                module._OBJC_OUTPUT_COLLECTOR_CLASS_NAME,
                module._OBJC_SCRIPT_RUNNER_CLASS_NAME,
            ],
        )

    def test_execute_code_runner_rejects_incompatible_abi_helper_class(self) -> None:
        module, _handler = self._load_module()
        self._configure_fake_objc(module, reset_registry=True)
        type(module._OBJC_OUTPUT_COLLECTOR_CLASS_NAME, (_FakeNSObject,), {"__module__": __name__})

        payload = json.loads(asyncio.run(module.execute_code("40 + 2")))

        self.assertFalse(payload["success"])
        self.assertIn("incompatible", payload["error"])
        self.assertIn(module._OBJC_OUTPUT_COLLECTOR_CLASS_NAME, payload["error"])


if __name__ == "__main__":
    unittest.main()
