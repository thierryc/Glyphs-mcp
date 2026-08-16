---
name: glyphs-mcp-maintainer-feedback
description: Turn a reproducible Glyphs MCP problem, audit discrepancy, or workflow limitation into a concise maintainer-ready report with redacted receipts, host versions, expected behavior, and safe reproduction steps.
---

# Glyphs MCP maintainer feedback

Prepare actionable feedback without leaking fonts, Python source, private paths, or recovery files.

## Core rules

- Reproduce with synthetic or disposable data whenever possible; never attach the production font by default.
- Capture `get_server_info`, the public capability manifest, host version/build, operation IDs, audit receipts, and bounded error codes.
- Include expected behavior, observed behavior, minimum steps, scope, frequency, and whether document or external state may have changed.
- Redact Python source, user paths, font content, recovery paths, and credentials. A code hash may be included.
- Distinguish deployment skew from a v2 API defect and state whether Glyphs was upgraded and restarted.
- Do not open an issue, send a message, upload an artifact, or expose a recovery copy without explicit user authorization.

## Workflow

1. Confirm the current runtime is API 2.0 and record the installed server version.
2. Reduce the report to one failing assertion or workflow using a disposable fixture.
3. Re-run the smallest relevant review or operation once and capture its typed result.
4. List safety impact: no change, verified rollback, recovery-only, stale state preserved, or external effects unverifiable.
5. Propose an acceptance test that would fail before the fix and pass afterward.
6. Present the maintainer-ready report for user review before any external submission.

## Deeper references

- [Contributing](https://github.com/thierryc/Glyphs-mcp/blob/main/CONTRIBUTING.md)
- [Safety model](https://github.com/thierryc/Glyphs-mcp/blob/main/content/concepts/safety-model.mdx)
