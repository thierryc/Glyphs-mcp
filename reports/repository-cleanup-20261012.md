# Repository consolidation — 12 October 2026

## Baseline and scope

The worktree was reconciled with published main `47a1fad5`, following the signed 2.0.4 source commit `1890d4ff` and promotion commit. The apparent local implementation diff matched the published source byte-for-byte; it was fast-forwarded rather than committed a second time. This follow-up updates documentation and preserves additional development evidence. It does not replace the signed 2.0.4 app or move its tag.

README, installation, troubleshooting, command/identity guidance, agent-package references, desktop build guidance and the repository website now describe 2.0.4/build 61, default Glyphs Python detection, conditional copy selection, installation override limits and private-runtime export verification. Managed release guidance is synchronized; the source skill digest changes accordingly, while the signed distribution retains its qualified digest.

The external-page brief includes replacement copy and publishing directions for Anotherplanet and the AP.CX Creative Foundry tool/experiment page, plus their index cards. Those external websites were inspected but not edited. The next-evolution handoff separates proposed priorities from implemented features.

## Preservation and cleanup

- All 89 initially changed/new files were backed up with a hash inventory before reconciliation. Thirty-three additional local files were restored and preserved in source, reports or optional material.
- The optional macro-iteration skill lives under `extras/`, outside the eleven managed release skills. No shared skill links or plugin caches were changed.
- Historical native probe files are retained with an index explaining their original versions and limits. Identifying workstation/guest paths in newly added public evidence are normalized; original local records remain in the recovery archive. Measurement values and failure evidence are retained.
- The cleanup tool removed 44 explicitly allowed compiler-cache/intermediate paths. Logs, test results, products, private runtime inputs, installed payloads and signed artifacts remain. A follow-up dry run finds no recognized outputs to remove. The logical-byte inventory includes cache files with different disk allocation; it is not a measurement of physical space recovered.
- Clean release-preparation source/baseline clones were relocated out of `build/` to a temporary preparation area. Logs, receipts and release distributions remain in their original evidence directories, with a relocation note.
- Six stale worktree registrations pointing to missing temporary directories were pruned. Active worktrees and unrelated branches were preserved. This worktree is named `lit/mcp-next`; main is updated separately in its primary checkout.
- Local-only routing and maintenance instructions remain excluded from Git. A recovery archive and cleanup receipts remain under ignored `build/repository-cleanup-20261012/`.

## Validation

86 focused Python checks passed for desktop build/cleanup protections, package isolation, documentation resources, release assets and Python detection. A further 44 package/build/routing/release checks passed: **130 distinct checks**, no failures. The new cleanup check proves retained products, test results, logs and runtime inputs survive cache removal; existing checks refuse source worktrees, tracked files and redirected outputs.

Managed-skill synchronization and lean package checks pass with **eleven skills, twenty tools and both runtime architectures**. Website TypeScript checking and the final production documentation build pass. The first documentation build encountered stale generated cache state; clearing only generated website output/cache resolved it. Whitespace checks pass.

No runtime implementation was changed during consolidation, and no new live-font or signed-distribution qualification is claimed. Published build-61 evidence remains in its separate report.
