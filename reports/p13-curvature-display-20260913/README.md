# P13 curvature display checkpoint

Source/runtime baseline: `ffb3e1c5` on `lit/v2-beta`. This commit preserves the paired P13 benchmark and proposals only; no implementation or skill fix is included.

Both versions pass 14/14 primary workflows and exact captured-data restoration. Read `report.md` for the partial-coverage, dirty-state, timing and qualification limits. V1 completes the observed UI/MCP workflow more effectively; the recommended v2 follow-up is focused skill guidance plus a compact companion coverage notice.

`evidence.tar.gz` contains the complete original report folder, raw public/native/UI logs, screenshots, fixture and generator, plus the referenced oracle/fixture/client dependencies and current coverage/deferred-v1 index. Every member has an independently verified SHA-256 in `evidence-manifest.json`. Paths are relative to the original workspace root. Extract into a **fresh directory**, then open the full report there so its relative evidence links resolve:

```sh
mkdir p13-evidence
tar -xzf evidence.tar.gz -C p13-evidence
# Full report: p13-evidence/reports/v1-v2/13-curvature-display/report.md
```

The original unpacked report remains in the parent worktree at `reports/v1-v2/13-curvature-display/report.md`. Historical native scripts contain explicit paths and require the recorded Glyphs/Python environment; read the specification before replaying. Extraction does not authorize an application restart, autosave change or user-font operation.

No release publication or v1 implementation change occurred. Unrelated working-tree edits are outside this checkpoint.
