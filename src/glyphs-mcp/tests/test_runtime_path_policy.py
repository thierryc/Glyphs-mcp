from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[3]
RESOURCES = REPO / "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Resources"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


policy = load("runtime_path_policy", RESOURCES / "runtime_path_policy.py")
probe = load("runtime_path_policy_probe_tests", RESOURCES / "runtime_probe.py")


class RuntimePathPolicyTests(unittest.TestCase):
    def test_external_python_orders_user_site_before_glyphs_fallback(self):
        plan = policy.build_runtime_path_plan(
            "/tmp/Glyphs 4/Scripts/site-packages",
            "/opt/homebrew/bin/python3",
            user_site="/tmp/python-user-site",
        )
        self.assertEqual(plan["runtimeKind"], "external")
        self.assertEqual(plan["installMode"], "user")
        self.assertEqual(
            plan["orderedRoots"],
            ["/tmp/python-user-site", "/tmp/Glyphs 4/Scripts/site-packages"],
        )

    def test_embedded_python_uses_glyphs_site_as_explicit_target(self):
        plan = policy.build_runtime_path_plan(
            "/tmp/Glyphs 3/Scripts/site-packages",
            "/Applications/Glyphs 3.app/Contents/Frameworks/Python.framework/Versions/3.11/bin/python3",
            user_site="/tmp/ignored-user-site",
        )
        self.assertEqual(plan["runtimeKind"], "embedded")
        self.assertEqual(plan["installMode"], "target")
        self.assertEqual(plan["orderedRoots"], ["/tmp/Glyphs 3/Scripts/site-packages"])

    def test_equivalent_roots_are_deduplicated_by_resolved_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            plan = policy.build_runtime_path_plan(
                alias, "/usr/bin/python3", user_site=real
            )
        self.assertEqual(len(plan["orderedRoots"]), 1)

    def test_apply_preserves_resource_and_stdlib_precedence(self):
        process_path = list(sys.path)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, fallback = root / "primary", root / "fallback"
            primary.mkdir()
            fallback.mkdir()
            entries = ["/plugin/resources", "/stdlib", "/old/site-packages", str(fallback)]
            plan = {
                "orderedRoots": [str(primary), str(fallback)],
            }
            policy.apply_runtime_path_plan(plan, path_entries=entries)
        self.assertEqual(entries[:2], ["/plugin/resources", "/stdlib"])
        self.assertEqual(entries[2:4], [str(primary), str(fallback)])
        self.assertEqual(sys.path, process_path)

    def test_symlink_between_approved_roots_is_accepted_but_escape_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, fallback, outside = root / "primary", root / "fallback", root / "outside"
            for path in (primary, fallback, outside):
                path.mkdir()
            approved_target = fallback / "fixture.py"
            approved_target.touch()
            approved_link = primary / "approved.py"
            approved_link.symlink_to(approved_target)
            outside_target = outside / "fixture.py"
            outside_target.touch()
            escaping_link = primary / "escaping.py"
            escaping_link.symlink_to(outside_target)
            plan = {"orderedRoots": [str(primary), str(fallback)]}
            accepted = policy.classify_origin(approved_link, plan)
            escaped = policy.classify_origin(escaping_link, plan)
        self.assertTrue(accepted["accepted"])
        self.assertEqual(escaped["code"], "symlink_escape")
        self.assertTrue(escaped["blocking"])

    def test_unrelated_origin_blocks(self):
        result = policy.classify_origin(
            "/tmp/unrelated/fixture.py", {"orderedRoots": ["/tmp/approved"]}
        )
        self.assertEqual(result["code"], "unexpected_origin")


class RuntimeProbePolicyTests(unittest.TestCase):
    def run_external(self, primary: Path, fallback: Path, module: str):
        with mock.patch.object(policy.site, "getusersitepackages", return_value=str(primary)):
            return probe.run_probe(
                mode="preinstall", site_packages=fallback, modules=[module]
            )

    def test_valid_primary_and_stale_fallback_warns(self):
        current = probe._expected_cpython_tag()
        stale = "311" if current != "311" else "314"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, fallback = root / "primary", root / "fallback"
            primary.mkdir(); fallback.mkdir()
            module = "fixture_duplicate"
            (primary / f"{module}.py").write_text("VALUE=1\n", encoding="utf-8")
            (fallback / f"{module}.cpython-{stale}-darwin.so").touch()
            result = self.run_external(primary, fallback, module)
            probe._clear_module(module)
        self.assertFalse(result["blocking"])
        self.assertTrue(any(i["code"] == "shadowed_duplicate" for i in result["issues"]))
        stale_issue = next(i for i in result["issues"] if i["code"] == "incompatible_abi")
        self.assertFalse(stale_issue["blocking"])

    def test_incompatible_primary_blocks(self):
        current = probe._expected_cpython_tag()
        stale = "311" if current != "311" else "314"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, fallback = root / "primary", root / "fallback"
            primary.mkdir(); fallback.mkdir()
            module = "fixture_bad_primary"
            (primary / f"{module}.cpython-{stale}-darwin.so").touch()
            (fallback / f"{module}.py").write_text("VALUE=1\n", encoding="utf-8")
            result = self.run_external(primary, fallback, module)
            probe._clear_module(module)
        issue = next(i for i in result["issues"] if i["code"] == "incompatible_abi")
        self.assertTrue(result["blocking"])
        self.assertTrue(issue["blocking"])

    def test_missing_primary_uses_valid_fallback_with_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, fallback = root / "primary", root / "fallback"
            primary.mkdir(); fallback.mkdir()
            module = "fixture_fallback"
            origin = fallback / f"{module}.py"
            origin.write_text("VALUE=1\n", encoding="utf-8")
            result = self.run_external(primary, fallback, module)
            probe._clear_module(module)
        self.assertFalse(result["blocking"])
        self.assertTrue(any(i["code"] == "fallback_selected" for i in result["issues"]))
        check = result["checks"][0]
        self.assertEqual(check["logicalOrigin"], str(origin))
        self.assertEqual(check["resolvedOrigin"], str(origin.resolve()))
        self.assertEqual(result["pathPlan"]["orderedRoots"], [str(primary), str(fallback)])

    def test_probe_accepts_cross_root_symlink_and_blocks_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            primary, fallback, outside = root / "primary", root / "fallback", root / "outside"
            primary.mkdir(); fallback.mkdir(); outside.mkdir()
            approved_name = "fixture_approved_link"
            approved_target = fallback / "approved_target.py"
            approved_target.write_text("VALUE=1\n", encoding="utf-8")
            (primary / f"{approved_name}.py").symlink_to(approved_target)
            escaped_name = "fixture_escaped_link"
            escaped_target = outside / "escaped_target.py"
            escaped_target.write_text("VALUE=1\n", encoding="utf-8")
            (primary / f"{escaped_name}.py").symlink_to(escaped_target)
            approved = self.run_external(primary, fallback, approved_name)
            escaped = self.run_external(primary, fallback, escaped_name)
            probe._clear_module(approved_name)
            probe._clear_module(escaped_name)
        self.assertFalse(approved["blocking"])
        self.assertTrue(escaped["blocking"])
        issue = next(i for i in escaped["issues"] if i["code"] == "symlink_escape")
        self.assertEqual(issue["logicalOrigin"], str(primary / f"{escaped_name}.py"))
        self.assertEqual(issue["resolvedOrigin"], str(escaped_target.resolve()))


if __name__ == "__main__":
    unittest.main()
