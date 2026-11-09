# Python test report

Pytest exit status: `0`.

| Product area | Passed | Failed/error | Skipped/xfail | Files | Test time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lean runtime and native bridge | 2133 | 0 | 2 | 83 | 213.22s |
| Public MCP tools | 377 | 0 | 0 | 30 | 4.44s |
| Installer and release | 341 | 0 | 0 | 23 | 46.44s |
| Font behavior and companions | 372 | 0 | 0 | 31 | 1.95s |
| Docs, skills, and host plugins | 65 | 0 | 1 | 12 | 4.77s |
| Other regressions | 170 | 0 | 0 | 18 | 17.19s |

## Non-passing tests

- `skipped` — `src/glyphs-mcp/tests/test_codex_plugin.py::AgentPluginTests::test_plugin_installs_in_an_isolated_copilot_home_when_available`: Skipped: GitHub Copilot CLI is unavailable
- `skipped` — `src/glyphs-mcp/tests/test_simple_v2_checkpoints.py::test_package_additions_and_deletions_are_exact[.glyphs]`: Skipped: package contract
- `skipped` — `src/glyphs-mcp/tests/test_simple_v2_feedback.py::test_server_and_stdio_proxy_advertise_the_same_offline_brand`: Skipped: Initialize response branding requires the locked runtime MCP SDK

Test time is the sum of pytest setup, call, and teardown durations; it is not wall-clock time.
