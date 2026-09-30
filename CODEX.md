# Glyphs MCP lean v2

Glyphs 4 uses the external sidecar, bounded native bridge, and independent
Curve Inspector and Reference Inspector. Glyphs 3 stays pinned to 1.11.0.
The current interface has thirteen tools; use the
[tool contract](content/reference/command-set.mdx) and
[Beta 8 milestones](BETA8-MILESTONES.md), not historical roadmaps, for scope.
Native scripts use `python_script` with `script.native.v1` in the conversation
workflow. Preparation never executes code or saves. Typed results retain
selective recovery; scripts restore the whole saved font and discard later
unsaved edits. Both offer Keep without saving and separately authorized Save.
Keep ends wrapper recovery and preserves native Undo/Redo. The retired
experimental runtime and script execution modes are not shipped.

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

Protect dependency boundaries, bounded reads/requests, the thirteen-tool surface,
capability negotiation and package isolation with behavioral tests. There are no
source-line budgets. Consolidate proven duplication; do not split code merely
to meet a file-length target. Preserve useful algorithms and external analysis/
export processing. Companion drawing callbacks only draw.

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
