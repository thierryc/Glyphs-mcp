---
name: glyphs-mcp-production-audit
description: Run a read-first production audit of a Glyphs source across compatibility, metrics inheritance, anchors, spacing, kerning coverage, instances, and export readiness using bounded v2 reviews and honest coverage accounting.
---

# Glyphs MCP production audit

Build an evidence-backed production report without silently changing or saving the font.

## Core rules

- Resolve one stable `documentId` and record its starting fingerprint and dirty state.
- Run independent reviews before proposing edits: `review_master_compatibility`, `review_metrics_inheritance`, `review_anchor_consistency`, `review_spacing`, `review_kerning_coverage`, and `review_export` when a destination is in scope.
- Follow paginated results through `get_operation`; do not infer completeness from the first page.
- Separate hard host/export failures from soft intentional design differences.
- Report measured, skipped, untested, and eligible kerning counts. Never label sampled coverage exhaustive.
- Do not apply, export, save, or run open-world Python unless the user separately requests the effect and confirms its review.

## Workflow

1. Capture server identity, document status, masters, instances, and glyph/kerning counts.
2. Review compatibility in both `component_preserving` and `decomposed_export` modes when export behavior could differ.
3. Review metrics-key/component inheritance and semantic anchor sets.
4. Run bounded five-iteration spacing simulation at the one-unit default tolerance; treat valid zero-width marks as skips.
5. Choose and state the kerning coverage mode. Use glyph expansion or class cross-product for an exhaustive claim.
6. Review export with `fail_if_nonempty` unless replacement of an exact destination fingerprint is explicitly intended.
7. Re-read the document fingerprint and report any drift during the audit.

## Output

Summarize hard blockers, soft findings, coverage gaps, actionable reviewed batches, response operation IDs, and whether the font remained unsaved.

## Deeper references

- [Safety model](https://github.com/thierryc/Glyphs-mcp/blob/main/content/concepts/safety-model.mdx)
- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
