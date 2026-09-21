# Test-suite review — 2026-09-20

## Decision

The suite is strong enough for day-to-day development and the current lean-v2
surface. It exercises the important failure modes, not just happy paths, and it
has unusually good explicit ownership for public tool behavior. It is not, by
itself, complete release evidence: native Glyphs behavior still needs the live
smoke matrix already identified by the release-gate tests.

This review deliberately does not quote a line-coverage percentage. The current
development environment has no coverage collector or enforced line/branch
threshold, so inventing a percentage would be misleading. The evidence below is
behavioral coverage: collected tests, public-surface ownership, native tests,
and real release paths.

## Verified baseline

| Gate | Result | Notes |
| --- | ---: | --- |
| Python/pytest | 2,043 passed, 2 skipped | 2,045 collected cases across 138 test modules; 57.17s wall time on Python 3.14.6 |
| macOS/XCTest | 203 passed | No failures or skips in the verified run |
| Public tool ownership | 87 of 87 | Every registered tool has a test owner, mutation class, undo risk, and reusable smoke prompt |
| Registration-only gaps | 0 | Enforced by `test_release_gate_tool_coverage.py` |
| Lean-v2 tool surface | 9 of 9 | Registration and service paths cover status, document discovery, reads, jobs, acceptance/discard, and explicit save |

The readable pytest report now groups results by user-facing product area:

| Product area | Passed | Skipped |
| --- | ---: | ---: |
| Lean runtime and native bridge | 1,032 | 0 |
| Public MCP tools | 377 | 0 |
| Installer and release | 260 | 1 |
| Font behavior and companions | 286 | 0 |
| Docs, skills, and host plugins | 58 | 1 |
| Other regressions | 30 | 0 |

## Coverage and test-quality review

### What is solid

- The lean-v2 tests follow the real request path through protocol validation,
  bridge behavior, sidecar service behavior, FastMCP registration, job state,
  apply/discard/accept, explicit Save/Save As, and installer payload identity.
- Pagination, stale cursors, bounded work, exact document/layer/master identity,
  dirty documents, unsaved documents, source hashes, target conflicts, rollback,
  and Undo/Redo are tested. These are the failure modes most likely to damage a
  font or return subtly wrong data.
- The suite includes real boundary checks where mocks would be misleading:
  localhost port reuse, FastMCP initialization, isolated CLI installation,
  native AppKit raster drawing, filesystem transactions, Git worktree reads,
  and the complete XCTest installer target.
- Public tools cannot silently appear without a release-gate entry. The current
  catalog classifies 56 tools as unit-behavior covered, one as unit-internal,
  and 30 as requiring additional live smoke; none is registration-only.
- Tests are deterministic and reasonably fast for their breadth. The full
  Python gate finishes in about one minute locally.

### Where unit coverage stops

- Thirty public tools intentionally require live smoke in Glyphs. The unit suite
  models native objects well, but it cannot prove host-version API behavior,
  actual document binding, drawing callbacks, menu/UI interaction, or the real
  undo stack. Release qualification must continue to run the listed Glyphs 3.5
  and Glyphs 4 smoke batches where applicable.
- No line or branch coverage threshold currently prevents an untested helper or
  branch from landing. The public-tool ownership matrix reduces that risk at the
  feature level but does not replace measured source coverage.
- A few files are very large (notably the main XCTest file and MCP helper/CLI
  test modules). Their assertions are useful, but future changes will be easier
  to review if tests are split by behavior as those files are touched.
- Four warnings come from the third-party `fs` package importing deprecated
  `pkg_resources` APIs. They do not invalidate the run, but they add noise and
  should be removed through a dependency update or a narrowly documented filter.

## Ignored-test disposition

| Previous condition | Decision | Reason |
| --- | --- | --- |
| Native AppKit candidate-overlay drawing was opt-in | Replaced with an ordinary runnable test in a fresh Python process | AppKit/Quartz are supported runtime dependencies; process isolation matches the plug-in launch boundary and avoids PyObjC's unsupported reload path |
| Eight XCTest Git scenarios skipped when Git was absent | Replaced with required assertions | The macOS project workflow and release gate require Git; absence is a broken prerequisite, not a valid untested configuration |
| Python 3.12/3.14 clean dependency install | Retained as an explicit release-only skip | It creates isolated environments and downloads the pinned runtime; `run_local_release_tests.sh` enables it with `GLYPHS_MCP_FULL_PYTHON_MATRIX=1` |
| GitHub Copilot CLI marketplace install | Retained as a host-availability skip | Copilot is a package-supported optional host, not an installed product prerequisite; manifest/schema/content contracts run unconditionally |
| Codex, Claude Code, Node.js, and symlink capability guards | Retained | They protect optional external-host or platform capability checks; all were runnable in this review environment except Copilot |

The ordinary Python run now reports only the two intentional conditional gates
above. Skips are listed by full test name and reason in the generated Markdown
report instead of being hidden among progress dots.

## Reporting changes

- `scripts/pytest_readable_report.py` adds a compact terminal table by product
  area and can emit the same results as Markdown.
- `pytest.ini` enables the summary for normal pytest runs and writes the current
  artifact to `build/test-report.md`.
- `scripts/run_python_tests.sh` now defaults to the complete pytest collection;
  `--unittest` remains available and is labeled as a compatibility subset. This
  prevents a normal developer run from silently omitting pytest-style lean tests.
- The report counts one logical test across setup/call/teardown, makes skips and
  expected failures explicit, and preserves pytest's normal failure details.
- The grouping/report code has focused tests so reporting cannot silently lose
  results or misclassify the main product areas.

## Recommended next step

Add measured branch coverage as a separate CI signal, initially informational,
for `src/protocol`, `src/bridge`, and `src/sidecar`. Set a threshold only after
excluding generated/package payloads and recording a trustworthy baseline. Keep
the live Glyphs matrix separate: a high Python percentage cannot substitute for
native host qualification.
