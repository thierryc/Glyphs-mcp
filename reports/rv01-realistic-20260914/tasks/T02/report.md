# T02 — Fractional width change and restoration

Route: **Public seven-tool MCP**. Font: pinned open-source Roboto Slab, three native masters.

The three +12.375 advances are exact. Every recorded non-width property and native object is preserved. Undo restores data and clears Edited; Redo replays exactly; discard restores exact data but leaves the native dirty indicator.

Final checks: 9 passed, 0 failed, 0 blocked, 0 unverified. See [exact assertions](assertions-final.json); earlier raw facts retain their first-attempt results.

LLM judgment: correctness evidence 5/5; design usefulness 4/5; focused skill 4/5; workflow effort 4/5. This is self-assessment by the executing LLM.

Instrumented public requests: 7; median 31.83 ms, range 16.62–47.88 ms, p95 46.26 ms. Different phases are mixed here; see the [call log](../../calls.jsonl). These are HTTP times, not native edit execution.

Suggested action: No product change justified by this case. Retain native dirty-state parity.

Preservation applies to recorded native coordinates, objects, hint references, metadata, anchors, widths, transforms and flags as covered by the oracle; all immutable source file bytes were separately hashed. The real edited layers have no hints, so populated-hint preservation is **unverified**.
