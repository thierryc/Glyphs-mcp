from __future__ import annotations

from types import SimpleNamespace

from scripts.pytest_readable_report import ReadableReport, markdown_report, product_area


def _phase(nodeid: str, when: str, outcome: str, *, duration: float = 0.01, reason=None):
    return SimpleNamespace(
        nodeid=nodeid,
        when=when,
        outcome=outcome,
        passed=outcome == "passed",
        failed=outcome == "failed",
        skipped=outcome == "skipped",
        duration=duration,
        longrepr=("test.py", 1, reason) if reason else None,
        wasxfail=False,
    )


def test_product_area_uses_real_product_boundaries() -> None:
    assert product_area("src/glyphs-mcp/tests/test_simple_v2_save.py::test_save") == "Lean runtime and native bridge"
    assert product_area("src/glyphs-mcp/tests/test_mcp_tools_font.py::test_fonts") == "Public MCP tools"
    assert product_area("src/glyphs-mcp/tests/test_install_cli.py::test_install") == "Installer and release"
    assert product_area("src/glyphs-mcp/tests/test_readable_test_report.py::test_report") == "Installer and release"
    assert product_area("src/glyphs-mcp/tests/test_spacing_engine.py::test_spacing") == "Font behavior and companions"
    assert product_area("src/glyphs-mcp/tests/test_docs_surface_sync.py::test_docs") == "Docs, skills, and host plugins"


def test_report_counts_one_result_across_all_pytest_phases() -> None:
    report = ReadableReport()
    nodeid = "src/glyphs-mcp/tests/test_simple_v2_save.py::test_save"
    report.record(_phase(nodeid, "setup", "passed"))
    report.record(_phase(nodeid, "call", "passed"))
    report.record(_phase(nodeid, "teardown", "passed"))

    row = report.rows()[0]
    assert row["passed"] == 1
    assert row["files"] == 1
    assert row["duration"] == 0.03


def test_markdown_report_makes_skips_and_passing_areas_visible() -> None:
    report = ReadableReport()
    passed = "src/glyphs-mcp/tests/test_mcp_tools_font.py::test_fonts"
    skipped = "src/glyphs-mcp/tests/test_python_runtime_matrix.py::test_matrix"
    report.record(_phase(passed, "call", "passed"))
    report.record(_phase(skipped, "setup", "skipped", reason="release gate only"))

    text = markdown_report(report, exitstatus=0)

    assert "| Public MCP tools | 1 | 0 | 0 | 1 |" in text
    assert "| Installer and release | 0 | 0 | 1 | 1 |" in text
    assert "`skipped`" in text
    assert "release gate only" in text
