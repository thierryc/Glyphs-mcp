---
name: glyphs-mcp-maintainer-feedback
description: Turn a reproducible Glyphs MCP problem, audit discrepancy, or workflow limitation into a concise maintainer-ready report with redacted receipts, host versions, expected behavior, and safe reproduction steps.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP maintainer feedback

Prepare actionable feedback without leaking fonts, Python source, private paths, or recovery files.

## Core rules

- Start with `get_server_info` and require `data.apiMajor == 2`. If it is absent
  or different, classify the report as runtime/deployment skew before testing
  any v2 behavior.
- Reproduce with synthetic or disposable data whenever possible; never attach the production font by default.
- Capture `get_server_info`, the public capability manifest, host version/build, operation IDs, audit receipts, and bounded error codes.
- Use `search_knowledge` and `get_knowledge` when expected behavior depends on
  Glyphs APIs, font formats, or typographic facts; include the stable evidence
  IDs and citations rather than relying on memory.
- Reproduce reads with `read_document`. Reproduce a document mutation through
  `preview_change` and the exact `apply_change` lifecycle on disposable data.
  If generic mechanics cannot express it, use the same permanent
  `execute_python` mode the report concerns and distinguish staged verification
  from `live_open_world` recovery evidence.
- Include expected behavior, observed behavior, minimum steps, scope, frequency, and whether document or external state may have changed.
- Redact Python source, user paths, font content, recovery paths, and credentials. A code hash may be included.
- Distinguish deployment skew from a v2 API defect and state whether Glyphs was upgraded and restarted.
- Do not open an issue, send a message, upload an artifact, or expose a recovery copy without explicit user authorization.

## Workflow

1. Confirm the current runtime is API 2.0 and record the installed server version.
2. Reduce the report to one failing assertion or workflow using a disposable fixture.
3. Re-run the smallest relevant generic read, immutable preview, exact apply,
   or Python fallback once and capture its typed result. Verify read-back and
   do not call `save_document`.
4. List safety impact: no change, verified rollback, recovery-only, stale state preserved, or external effects unverifiable.
5. Propose an acceptance test that would fail before the fix and pass afterward.
6. Present the maintainer-ready report for user review before any external submission.

## Deeper references

- [Contributing](https://github.com/thierryc/Glyphs-mcp/blob/main/CONTRIBUTING.md)
- [Safety model](https://github.com/thierryc/Glyphs-mcp/blob/main/content/concepts/safety-model.mdx)
