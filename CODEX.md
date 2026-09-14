# Glyphs MCP lean v2

Glyphs 4 uses the external sidecar, bounded native bridge, and independent
Curve Inspector and Reference Inspector. Glyphs 3 stays pinned to 1.11.0.
The seven MCP tools are get_status, list_documents, read_entities, start_job,
get_job, apply_job and discard_job. Native Save is acceptance; Undo and Redo
are per glyph, and discard restores a whole job. No remote arbitrary Python
execution or experimental canonical runtime is shipped.

Production source lives in src/sidecar, src/bridge, src/protocol and
src/companions. Workflows belong outside the bridge. Keep the existing source
protection, exact history/recovery, target-level concurrency and cancellation.
Proposal/display tolerance is 0.001 font units, with zero relative tolerance;
it never weakens exact restoration or topology checks.

Build with scripts/build_simple_v2.py and scripts/build_installer_payload.py.
Build the desktop app with `python scripts/build_local_app.py`; it uses fresh
DerivedData and verifies the compiled asset catalog. Install only
`dist/local/Glyphs MCP.app` after `scripts/verify_desktop_app.py` passes with
`--receipt dist/local/build-receipt.json`. Never reuse or copy DerivedData
between worktrees. Use `scripts/clean_desktop_builds.py --apply` for obsolete
generated outputs; never remove `build/` wholesale or create worktrees in it.
Private runtimes are built from third_party/lean-runtime*.json and hash locks
using scripts/build_private_runtime.py. Downloads are a maintainer preparation
step, never an end-user installation step. The installer copies selected
components transactionally, preserving unrelated files and preferences.

Core budgets: protocol 350 lines, bridge 1600, sidecar 3500, total 6000, each
module at most 500. Share mechanisms and remove duplication rather than
adding scenario-specific handlers. Companion drawing callbacks only draw.

Run focused pytest checks, then scripts/run_python_tests.sh --pytest, native
installer tests, deterministic builds, docs/skills checks and git diff --check.
Use an authorized disposable font for native acceptance, verify the original
source hash, and report baseline and loaded responsiveness separately. A
200 ms HTTP sample is diagnostic, not an automatic release rejection.

The canonical lean agent skills are in skills/; synchronize packaged copies
with scripts/sync_codex_plugin_skills.sh. Pinned Glyphs 3 skills are preserved
in legacy/glyphs3. Keep local preparation separate from public release.

Use [the qualification index](reports/README.md) for the latest tested state and
remaining limits. Preserve historical reports and evidence; add a dated follow-up
instead of rewriting measurements. Validate the current skill payload with
`python scripts/check_lean_package.py` and
`bash scripts/sync_codex_plugin_skills.sh --check`. Keep focused instructions in
linked references rather than repeating them in every entry skill.
