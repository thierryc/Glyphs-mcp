# Python test report

Pytest exit status: `0`.

| Product area | Passed | Failed/error | Skipped/xfail | Files | Test time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lean runtime and native bridge | 1469 | 0 | 1 | 65 | 197.39s |
| Public MCP tools | 377 | 0 | 0 | 30 | 5.57s |
| Installer and release | 269 | 0 | 0 | 21 | 47.99s |
| Font behavior and companions | 286 | 0 | 0 | 27 | 1.32s |
| Docs, skills, and host plugins | 58 | 0 | 1 | 11 | 5.15s |
| Other regressions | 33 | 0 | 0 | 6 | 1.79s |

## Non-passing tests

- `skipped` — `src/glyphs-mcp/tests/test_codex_plugin.py::AgentPluginTests::test_plugin_installs_in_an_isolated_copilot_home_when_available`: Skipped: GitHub Copilot CLI is unavailable
- `skipped` — `src/glyphs-mcp/tests/test_simple_v2_checkpoints.py::test_package_additions_and_deletions_are_exact[.glyphs]`: Skipped: package contract

Test time is the sum of pytest setup, call, and teardown durations; it is not wall-clock time.
