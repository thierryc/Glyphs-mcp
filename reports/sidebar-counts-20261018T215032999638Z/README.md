# Sidebar count experiment — October 18, 2026

**Result: failed or blocked; native suppression effectiveness is unqualified.**

The final source was launched through `scripts/run_sidebar_count_experiment.py`
using the default five repetitions and 180-second per-process watchdog. The
plugin-free isolated host was Glyphs 4.2, build 4202.0 (`GSApplication`). It
constructed and retained a synthetic two-master, 1,000-glyph fixture, covering
six categories and Latin, Arabic and Han scripts, with 200 control glyphs.

Native Font View initialization stopped at `GSDocument.makeWindowControllers()`:

```text
NSInternalInconsistencyException — Cannot find value transformer with name GSLocalNumberFormatTransformer
```

No attached sidebar was qualified, no count flags were changed and no MCP
workload ran. **0 of the planned 20 matrix runs completed.** The harness did not
fall back to the working editor, replace the missing transformer, install a
runtime or restart Glyphs. This is a host UI initialization blocker, not a
reproduction of the original sidebar-filter exception.

Evidence:

- `summary.json`: complete source hashes, planned matrix, launch command and outcome.
- `preflight/result.json`: app identity, fixture properties and native traceback.
- `preflight/supervisor.json`: process exit status and wall time.
- `preflight/stdout.log`, `preflight/stderr.log`: native process output.
- `preflight/Disposable.glyphs`: generated fixture; no user font was used.
- `regression-tests.md`: 123 passing focused tests, including 28 new experimental tests.

The focused suite covered exact-name/layer targeting, changed selection, missing
owners, interface restoration, mixed original suppression flags, partial guard
setup failure, cleanup failure, actual BridgeCore success/failure/cancellation
with native doubles, and external watchdog timeout/alert handling. Those checks
do not establish live UI efficacy. Skill synchronization and the lean package
checker also passed; production bridge/sidecar/protocol source was unchanged.

Earlier development attempts remain in sibling report directories. The first
exposed an Undo-registration error during fixture setup; detached construction
corrected it. The second reached the same missing-transformer blocker. This
directory is the final-source run, and its source hashes are the qualification
reference. Automatic sidebar suppression remains off.
