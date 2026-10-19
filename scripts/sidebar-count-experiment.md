# Sidebar count experiment

This is a development qualification harness, not an installed feature. It never
changes production bridge behavior or connects to the working Glyphs session.

Run from the checkout with the development Python environment:

```sh
python3 scripts/run_sidebar_count_experiment.py
```

The supervisor uses `glyphs run --app '/Applications/Glyphs 4.app' --plugins ''`
in a new process group. Override `--cli` and `--app` for another installed host.
Each run gets a new report directory; `--report` must name a nonexistent path.
The default is five repetitions per variant and a 180-second process timeout.
Reduced `--repeats` is useful for development but is not the prescribed five-run
qualification. Run the supervisor, not the native child script in an editor.

Preflight builds a two-master, 1,000-glyph synthetic font with Latin, Arabic, Han,
marks, numbers, punctuation, separators and symbols. Components reference an
untouched control glyph. It requires a visible native Font View, an attached
sidebar, font-owned predicate items and a computed native count. An unavailable
UI blocks the entire matrix; detached predicate success cannot substitute for it.

On Glyphs 4.2 (4202), the CLI preflight currently blocks because its application
bootstrap lacks classes supplied by the full GUI executable. Do not remove the
Font View requirement or substitute nib-class shims to get a passing result.
The full-editor route now qualifies a real Font View in VirtualBuddy on Glyphs
4.2 (4202). Its run-specific external supervisor and evidence are recorded in
`reports/sidebar-font-view-vm-20261018/`. The older guest-installed 4.1.1 (4108)
was not used for the comparison. The host working Glyphs session is untouched.

The full editor opens the fixture through NSDocumentController's normal file
read path. Setup and bridge queue callbacks return to the actual application
event loop between turns. A nested run loop inside one long callback does not
allow the sidebar's main-dispatch completion to install its background-built
model. The child uses bounded one-shot timers rather than replacing native
classes or bypassing the attached-sidebar check. It verifies glyph membership
and both master IDs again after normal document opening, which may reorder
glyphs without changing their identities.

The VM supervisor verifies the pristine app and source archive hashes, checks
the app signature inside and outside the child sandbox, and starts a fresh
full-editor process for each case. Each child has private plugin/support paths
and denies reads of the original guest third-party plugin directories. It uses
the guest's existing native Python framework and normal trial preferences;
the VM is the filesystem isolation boundary. No host preferences or license
are copied. Routine trial continuation is handled in the VM UI, without a
global error-dismissal hook. Startup has a separate 900-second bound to allow
that interaction; workloads retain a 180-second bound.

The native child retains a real diagnostic file while importing the shared
harness, so its faulthandler timer also works with the full editor's descriptor-
less `GlyphsErr` stream. That timer is cancelled before its file is closed.

Each matrix run uses the real in-process SidecarService/BridgeCore workflow to
change colors, replace paths/components and add explicitly named glyphs. HTTP,
installed runtime/client transport and editor Save are not qualified. Exact
requests, workflow IDs and native logs are retained. No invalid filter is added.

The experimental guard preflights ownership/accessors, snapshots unselected
predicate items' flags, suppresses counts, and restores exact original values.
It remains active through interface refresh and two seconds of normal event-loop
settling; another two-second observation follows restoration. Settling is a
bounded observation, not proof that native background work has drained. Selected
predicates and queued calculations remain limitations. The source variants alter
only batching and suppression; no production protocol option is introduced.

The process-local window observer records native sidebar alerts without closing
or hiding them. The external supervisor terminates only its spawned process
group after an observed alert or timeout. A modal hang that prevents observation
is a timeout failure, not evidence that no alert occurred. Script recovery does
not restore UI controller flags: the guard has independent cleanup. Cleanup
failures remain in evidence, and crashed/terminated runs cannot claim restoration.

`summary.json` distinguishes **promising mitigation**, **not reproduced**, and
**failed or blocked**. Promising requires baseline alert reproduction and every
run of at least one suppression variant passing. A clean matrix is only
not-reproduced evidence. Preflight failure runs none of the matrix cases.
Exit code 2 indicates failed/blocked qualification; 0 indicates a completed
not-reproduced or promising matrix, not a product fix.

Focused regression tests are in `test_sidebar_count_experiment.py`. They exercise
exact targets, changed selection, missing owners, mixed suppression flags,
partial setup and restoration failures, bridge success/failure/cancellation, and
the external watchdog. No live installation or restart is part of this harness.

The October 18 VirtualBuddy run completed all 20 prescribed fresh-process cases
on 4202: five of five passed for every variant, with 60 completed workflows and
no observed filter alerts, timeouts or cleanup errors. Classification is **not
reproduced**; suppression effectiveness is unproven. See
`reports/sidebar-font-view-vm-20261018/summary.json` and its README for identities,
per-case evidence and limitations. Failure/cancellation/mixed-flag scenarios are
regression tests, while this native matrix covers successful workloads. Keep
automatic suppression off pending a separate integration decision.
