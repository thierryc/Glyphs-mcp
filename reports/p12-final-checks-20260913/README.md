# Final P12 qualification evidence

Source/runtime checkpoint: `2157efe23caf8ecd2d2b34c6e61dd9f5cecdde3c` on `lit/v2-beta`. This follow-up records the remaining native tests without changing that runtime or installed skills.

Read `report.md` for results. All four outstanding checks executed with periodic autosaving enabled at eight seconds. Cubic native Undo/Redo/discard and the unique-name bound pass. Native callback p95 23.20 ms, queue-lag p95 5.49 ms; exact 90-layer profile restoration passes. Stored component data restores exactly; derived bounds and dirty-flag findings remain documented. No crash through the 131.518-second cleanup observation. P13 curvature display is next; it has not been run.

`evidence.tar.gz` holds the complete final session, including the raw v2 proofs and executable historical harness. Every member's SHA-256 is in `evidence-manifest.json` and was checked after compression. Extract it into this directory to resolve the report's relative evidence links:

```sh
tar -xzf evidence.tar.gz
```

The harness contains explicit paths for the recorded machine and disposable fixture. Read its specification before any replay; extracting evidence does not authorize native actions or an autosave pause. Original files remain unchanged in the parent worktree. The preceding full P12 evidence is preserved in `../p12-checkpoint-20260913/p12-evidence.tar.gz`. No source/skill edit, release publication or v1 modification occurred in this follow-up.
