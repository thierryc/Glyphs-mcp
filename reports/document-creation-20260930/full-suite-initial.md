# Python test report

Pytest exit status: `1`.

| Product area | Passed | Failed/error | Skipped/xfail | Files | Test time |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lean runtime and native bridge | 1465 | 3 | 1 | 65 | 154.90s |
| Public MCP tools | 377 | 0 | 0 | 30 | 5.52s |
| Installer and release | 251 | 11 | 1 | 20 | 9.12s |
| Font behavior and companions | 286 | 0 | 0 | 27 | 1.37s |
| Docs, skills, and host plugins | 56 | 2 | 1 | 11 | 4.60s |
| Other regressions | 31 | 2 | 0 | 6 | 1.59s |

## Non-passing tests

- `skipped` — `src/glyphs-mcp/tests/test_codex_plugin.py::AgentPluginTests::test_plugin_installs_in_an_isolated_copilot_home_when_available`: Skipped: GitHub Copilot CLI is unavailable
- `skipped` — `src/glyphs-mcp/tests/test_python_runtime_matrix.py::PythonRuntimeMatrixTests::test_requirements_install_and_import_under_python_312_and_314`: Skipped: set GLYPHS_MCP_FULL_PYTHON_MATRIX=1 to run full Python dependency verification
- `skipped` — `src/glyphs-mcp/tests/test_simple_v2_checkpoints.py::test_package_additions_and_deletions_are_exact[.glyphs]`: Skipped: package contract
- `failed` — `src/glyphs-mcp/tests/test_desktop_build.py::test_new_source_asset_must_be_in_compiled_catalog`
- `failed` — `src/glyphs-mcp/tests/test_desktop_build.py::test_receipt_binds_app_to_worktree_and_source[app]`
- `failed` — `src/glyphs-mcp/tests/test_desktop_build.py::test_receipt_binds_app_to_worktree_and_source[none]`
- `failed` — `src/glyphs-mcp/tests/test_desktop_build.py::test_receipt_binds_app_to_worktree_and_source[source]`
- `failed` — `src/glyphs-mcp/tests/test_desktop_build.py::test_receipt_binds_app_to_worktree_and_source[worktree]`
- `failed` — `src/glyphs-mcp/tests/test_desktop_build.py::test_rejects_missing_pierre_resource_bundle`
- `failed` — `src/glyphs-mcp/tests/test_desktop_build.py::test_rejects_modified_pierre_javascript`
- `failed` — `src/glyphs-mcp/tests/test_desktop_build.py::test_rejects_old_asset_catalog_even_when_version_and_executable_match`
- `failed` — `src/glyphs-mcp/tests/test_desktop_management.py::test_authenticated_private_routes_and_unchanged_public_tools`
- `failed` — `src/glyphs-mcp/tests/test_docs_surface_sync.py::DocsSurfaceSyncTests::test_lean_readme_and_reference_describe_exactly_the_shipped_catalog`
- `failed` — `src/glyphs-mcp/tests/test_docs_versioning.py::test_v2_catalog_signatures_match_the_base_and_workflow_tools`
- `failed` — `src/glyphs-mcp/tests/test_h2_setup_identity.py::test_identity_table_matches_release_source_protocol_and_inventory`
- `failed` — `src/glyphs-mcp/tests/test_h2_setup_identity.py::test_release_skill_reference_is_local_synchronized_and_matches_release`
- `failed` — `src/glyphs-mcp/tests/test_lean_package_check.py::test_catalog_check_rejects_renamed_or_duplicate_tools_even_with_twelve_declarations[renamed_tool]`
- `failed` — `src/glyphs-mcp/tests/test_lean_package_check.py::test_catalog_check_rejects_renamed_or_duplicate_tools_even_with_twelve_declarations[tool_1]`
- `failed` — `src/glyphs-mcp/tests/test_simple_v2_build.py::test_build_is_deterministic_and_excludes_the_old_runtime`
- `failed` — `src/glyphs-mcp/tests/test_simple_v2_server_control.py::test_live_reusable_listener_still_blocks_port_change`
- `failed` — `src/glyphs-mcp/tests/test_simple_v2_server_control.py::test_port_can_return_to_a_closed_listener_with_recent_connections`

Test time is the sum of pytest setup, call, and teardown durations; it is not wall-clock time.
