# Python test report

Pytest exit status: `0`.

| Product area | Passed | Failed/error | Skipped/xfail | Files | Test time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lean runtime and native bridge | 1135 | 0 | 0 | 48 | 51.51s |
| Public MCP tools | 377 | 0 | 0 | 30 | 5.31s |
| Installer and release | 262 | 0 | 1 | 20 | 7.77s |
| Font behavior and companions | 286 | 0 | 0 | 27 | 1.19s |
| Docs, skills, and host plugins | 58 | 0 | 1 | 11 | 4.39s |
| Other regressions | 30 | 0 | 0 | 6 | 1.72s |

## Non-passing tests

- `skipped` — `src/glyphs-mcp/tests/test_codex_plugin.py::AgentPluginTests::test_plugin_installs_in_an_isolated_copilot_home_when_available`: Skipped: GitHub Copilot CLI is unavailable
- `skipped` — `src/glyphs-mcp/tests/test_python_runtime_matrix.py::PythonRuntimeMatrixTests::test_requirements_install_and_import_under_python_312_and_314`: Skipped: set GLYPHS_MCP_FULL_PYTHON_MATRIX=1 to run full Python dependency verification

Test time is the sum of pytest setup, call, and teardown durations; it is not wall-clock time.
