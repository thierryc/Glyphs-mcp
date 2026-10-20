# VirtualBuddy Font View qualification — October 18, 2026

The real full-editor Font View and sidebar now qualify in the VirtualBuddy VM
`Beztrace-0.2.0-qualification`. The completed matrix is in `attempt-225812/`; the aggregate is `summary.json`.
This investigation did not edit, restart or install anything into the host
working Glyphs session. Automatic suppression remains off.

The successful route uses a pristine copy of Glyphs **4.2 (4202)**, with verified
archive/executable hashes and strict signature checks. It uses the guest's
existing native Python 3.14 framework. The guest-installed **4.1.1 (4108)** was
quit with no fonts open and was not used to qualify the reported 4202 issue.
No host license, credentials or preferences were copied, and no runtime was
installed. Third-party plugin fallback paths are denied to each test child;
only the test-owned diagnostic loader is in its private support directory.
The VM is the filesystem isolation boundary; normal guest trial preferences
and ordinary guest network/file access are used.

The key fix is returning to the real application event loop. Glyphs builds the
sidebar model in background work and installs it through the main dispatch
queue. Spinning a nested run loop inside a single long plugin callback left
that completion unable to run. The native qualifier now opens the synthetic
fixture through the normal NSDocumentController document-read path and uses
bounded one-shot timer turns for setup and bridge queue callbacks. It verifies
all names and both master IDs after opening. The normal reader reorders glyphs;
this is recorded and does not alter the fixed explicit name/layer manifest.
Every qualified process sees a visible Font View, attached sidebar, 46 owned
predicate items and a computed native count. Detached predicate success was
never accepted as UI qualification.

The native child also retains a real stderr file while importing the shared
native harness, because the full editor's GlyphsErr stream lacks fileno. The
faulthandler timer is cancelled before closing that file. Regression tests cover
this boundary and the asynchronous real-loop dispatcher.

`vm_driver_11.py` is the exact run-specific external supervisor. It is restricted
to a VirtualMac model, checks app/source identities, launches a fresh process
for each case, and terminates only its own process group. It allows 900 seconds
for trial/UI startup and 180 seconds after workloads start. A routine Continue
Trial notice requires UI continuation per fresh process; the user previously
reviewed and accepted the agreement. No filter alerts are dismissed globally.
The child remains suppressed through interface refresh and two seconds of
normal event-loop settling, restores original flags, then observes two more
seconds. Interface batching is not a background-worker lock.

The matrix ran baseline, batching-only, suppression-only and combined,
five fresh processes each. Each process exercises colors, shape/component
replacement and glyph addition through real in-process SidecarService/BridgeCore
workflows. Each fixture starts with two masters, 1,000 diverse glyphs and 200
untouched controls. HTTP and installed-client MCP transport are outside this
qualification; the bounded host/guest HTTP endpoints only transfer source files
and read evidence. Results include requests, workflow/job IDs, logs, timings,
source hashes, app identity and independent cleanup verification.

Earlier `attempt-*` directories retain startup failures and blocked preflights.
They document CLI/full-editor bootstrap differences, guest CSSM failures from
overrestrictive write denial, a Plugin Manager startup error under network
denial, and the original empty sidebar model. These attempts are not matrix
measurements and do not count as reproduction of the sidebar filter alert.

**Classification: not reproduced.** All 20 matrix runs passed, with no observed
filter alerts, timeouts or cleanup errors. Each variant passed five of five
fresh-process runs, totaling 60 completed workflows. Every run verified exact
edit results, 200 untouched controls, original suppression/interface flags,
unchanged predicates and selection, and responsiveness after restoration.
The clean baseline leaves suppression effectiveness unproven. No production
suppression or bridge integration is enabled.

| Variant | Passed | Alerts | Cleanup errors |
| --- | ---: | ---: | ---: |
| Baseline | 5/5 | 0 | 0 |
| Batching only | 5/5 | 0 | 0 |
| Suppression only | 5/5 | 0 | 0 |
| Combined | 5/5 | 0 | 0 |

`validation.json` and the two test reports record 131 passing focused tests,
including 31 harness regressions, plus skill synchronization, lean-package and
diff checks. Missing targets, changed selection, mixed initial flags, injected
script failure, cancellation between callbacks and restoration failure are
covered by regression tests. They were not injected into the native matrix.

All test Glyphs children were terminated by their owning external supervisor
after recording results. Exit code -15 in a completed case is that deliberate
post-verification termination. The guest evidence endpoint closes automatically
20 minutes after completion; it exposes only status and report downloads to the
host. It has no remote command endpoint. Launch times include manual trial
continuation and should not be used to compare workload performance.

Repeated fixture files and exact workload requests are published as deterministic
`.gz` copies. Decompress to their original filenames to inspect them; the raw
local evidence is preserved. Recorded original run paths and source hashes retain
their original scope.
