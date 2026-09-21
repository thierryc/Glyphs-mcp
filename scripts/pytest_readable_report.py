"""Small pytest plug-in for a product-oriented passing-test report.

The repository has enough tests that a stream of dots or file names no longer
answers the useful question: which user-facing parts of Glyphs MCP passed?  This
plug-in keeps pytest's normal failure output and adds a compact area summary.  A
Markdown copy is written when ``--test-report`` is configured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


STATUS_ORDER = {
    "passed": 0,
    "xfailed": 1,
    "skipped": 2,
    "xpassed": 3,
    "failed": 4,
    "error": 5,
}

AREA_ORDER = (
    "Lean runtime and native bridge",
    "Public MCP tools",
    "Installer and release",
    "Font behavior and companions",
    "Docs, skills, and host plugins",
    "Other regressions",
)


def product_area(nodeid: str) -> str:
    """Map a test to the product behavior it protects, not its test framework."""
    filename = Path(nodeid.split("::", 1)[0]).name
    stem = filename.removeprefix("test_").removesuffix(".py")

    if stem.startswith("simple_v2_"):
        return AREA_ORDER[0]
    if stem.startswith(("mcp_tool", "tool_", "security_error", "code_execution")):
        return AREA_ORDER[1]
    if stem.startswith(
        (
            "beta",
            "bump_version",
            "desktop",
            "h2_setup",
            "install_cli",
            "plugin_manager",
            "python_runtime",
            "readable_test_report",
            "release",
            "runtime_probe",
            "update",
        )
    ):
        return AREA_ORDER[2]
    if stem.startswith(
        (
            "candidate",
            "compensated",
            "curve",
            "cyclic",
            "document_change",
            "export_designspace",
            "glyph_diff",
            "glyphs_candidate",
            "glyphs_curve",
            "glyphs_icon",
            "glyphs_litsquare",
            "icon_grid",
            "italic",
            "kerning",
            "litsquare",
            "outline",
            "smoothness",
            "spacing_engine",
            "unicode",
        )
    ):
        return AREA_ORDER[3]
    if stem.startswith(
        (
            "codex_plugin",
            "development_skill",
            "docs_",
            "documentation",
            "guide_resources",
            "llm_tool_routing",
            "outlines_skill",
            "skill_",
            "spacing_skill",
        )
    ):
        return AREA_ORDER[4]
    return AREA_ORDER[5]


def _skip_reason(report: Any) -> str | None:
    longrepr = getattr(report, "longrepr", None)
    if isinstance(longrepr, tuple) and len(longrepr) >= 3:
        return str(longrepr[2])
    if longrepr:
        return str(longrepr).strip().splitlines()[-1]
    return None


@dataclass
class TestResult:
    area: str
    path: str
    status: str = "passed"
    duration: float = 0.0
    reason: str | None = None


@dataclass
class ReadableReport:
    results: dict[str, TestResult] = field(default_factory=dict)

    def record(self, report: Any) -> None:
        nodeid = report.nodeid
        result = self.results.setdefault(
            nodeid,
            TestResult(area=product_area(nodeid), path=nodeid.split("::", 1)[0]),
        )
        result.duration += float(getattr(report, "duration", 0.0))

        status: str | None = None
        reason: str | None = None
        was_xfail = bool(getattr(report, "wasxfail", False))
        if report.when == "call":
            if was_xfail and report.skipped:
                status, reason = "xfailed", str(report.wasxfail)
            elif was_xfail and report.passed:
                status, reason = "xpassed", str(report.wasxfail)
            elif report.failed:
                status = "failed"
            elif report.skipped:
                status, reason = "skipped", _skip_reason(report)
            elif report.passed:
                status = "passed"
        elif report.failed:
            status = "error"
        elif report.skipped:
            status, reason = "skipped", _skip_reason(report)

        if status is not None and STATUS_ORDER[status] >= STATUS_ORDER[result.status]:
            result.status = status
            result.reason = reason

    def rows(self) -> list[dict[str, Any]]:
        rows = []
        for area in AREA_ORDER:
            values = [result for result in self.results.values() if result.area == area]
            if not values:
                continue
            counts = {status: 0 for status in STATUS_ORDER}
            for result in values:
                counts[result.status] += 1
            rows.append(
                {
                    "area": area,
                    **counts,
                    "files": len({result.path for result in values}),
                    "duration": sum(result.duration for result in values),
                }
            )
        return rows

    def exceptions(self) -> list[tuple[str, TestResult]]:
        return sorted(
            (
                (nodeid, result)
                for nodeid, result in self.results.items()
                if result.status != "passed"
            ),
            key=lambda item: (STATUS_ORDER[item[1].status], item[0]),
        )


def terminal_lines(report: ReadableReport) -> list[str]:
    header = f"{'Product area':35}  {'Pass':>5} {'Fail':>5} {'Skip':>5} {'Files':>5} {'Time':>8}"
    lines = [header, "-" * len(header)]
    for row in report.rows():
        failed = row["failed"] + row["error"] + row["xpassed"]
        skipped = row["skipped"] + row["xfailed"]
        lines.append(
            f"{row['area']:35}  {row['passed']:5d} {failed:5d} {skipped:5d} "
            f"{row['files']:5d} {row['duration']:7.2f}s"
        )
    return lines


def markdown_report(report: ReadableReport, exitstatus: int) -> str:
    lines = [
        "# Python test report",
        "",
        f"Pytest exit status: `{exitstatus}`.",
        "",
        "| Product area | Passed | Failed/error | Skipped/xfail | Files | Test time |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report.rows():
        failed = row["failed"] + row["error"] + row["xpassed"]
        skipped = row["skipped"] + row["xfailed"]
        lines.append(
            f"| {row['area']} | {row['passed']} | {failed} | {skipped} | "
            f"{row['files']} | {row['duration']:.2f}s |"
        )

    exceptions = report.exceptions()
    if exceptions:
        lines.extend(["", "## Non-passing tests", ""])
        for nodeid, result in exceptions:
            detail = f": {result.reason}" if result.reason else ""
            lines.append(f"- `{result.status}` — `{nodeid}`{detail}")
    else:
        lines.extend(["", "All collected tests passed."])
    lines.extend(
        [
            "",
            "Test time is the sum of pytest setup, call, and teardown durations; it is not wall-clock time.",
            "",
        ]
    )
    return "\n".join(lines)


_ACTIVE_REPORT: ReadableReport | None = None


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("glyphs-mcp-report")
    group.addoption(
        "--readable-report",
        action="store_true",
        help="Summarize passing tests by Glyphs MCP product area.",
    )
    group.addoption(
        "--test-report",
        metavar="PATH",
        help="Write the product-area test summary as Markdown.",
    )


def pytest_configure(config: Any) -> None:
    global _ACTIVE_REPORT
    if config.getoption("readable_report") or config.getoption("test_report"):
        _ACTIVE_REPORT = ReadableReport()


def pytest_unconfigure(config: Any) -> None:
    global _ACTIVE_REPORT
    _ACTIVE_REPORT = None


def pytest_runtest_logreport(report: Any) -> None:
    if _ACTIVE_REPORT is not None:
        _ACTIVE_REPORT.record(report)


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: Any) -> None:
    if _ACTIVE_REPORT is None:
        return
    if config.getoption("readable_report"):
        terminalreporter.write_sep("=", "passing tests by product area")
        for line in terminal_lines(_ACTIVE_REPORT):
            terminalreporter.write_line(line)

    output = config.getoption("test_report")
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown_report(_ACTIVE_REPORT, exitstatus), encoding="utf-8")
        terminalreporter.write_line(f"Markdown test report: {path}")
