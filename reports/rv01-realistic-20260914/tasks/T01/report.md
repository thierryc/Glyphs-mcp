# T01 — Live layer and selection inspection

Route: **Public seven-tool MCP**. Font: pinned open-source Roboto Slab, three native masters.

Twelve layer IDs, advances and bounds and three selected nodes agree with the native oracle. Bounded and empty reads are explicit. The agent used the wrong selector key in an extra missing-glyph control; its named-target assertion remains unverified.

Final checks: 41 passed, 0 failed, 0 blocked, 1 unverified. See [exact assertions](assertions-final.json); earlier raw facts retain their first-attempt results.

LLM judgment: correctness evidence 4/5; design usefulness 4/5; focused skill 4/5; workflow effort 3/5. This is self-assessment by the executing LLM.

Instrumented public requests: 3; median 33.73 ms, range 23.71–2091.88 ms, p95 1886.06 ms. Different phases are mixed here; see the [call log](../../calls.jsonl). These are HTTP times, not native edit execution.

Suggested action: Use the documented glyph selector id; avoid guessing field names.

Preservation applies to recorded native coordinates, objects, hint references, metadata, anchors, widths, transforms and flags as covered by the oracle; all immutable source file bytes were separately hashed. The real edited layers have no hints, so populated-hint preservation is **unverified**.
