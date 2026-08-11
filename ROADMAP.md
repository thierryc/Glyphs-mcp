# Glyphs MCP roadmap

This roadmap ranks possible additions by expected user value first and relative
implementation complexity second. Items 1–3 form the Glyphs MCP 1.9 milestone.
Everything after that milestone is directional: order and scope may change, and
these entries are not release commitments.

## 1.9 milestone: one-document change overview

Glyphs MCP 1.9 establishes an authoritative, memory-only record of MCP
activity for one live Glyphs document during the current Glyphs run. It is an
activity record, not a semantic before/after source diff. It never edits or
saves the font.

The milestone is available through the read-only
`get_document_change_overview` tool and through **Edit → Glyphs MCP Changes…**
inside Glyphs. The native panel remains usable while the server is stopped.

| Rank | Addition | Value | Relative complexity | Dependencies | Status |
| ---: | --- | --- | --- | --- | --- |
| 1 | Consistent mutation summaries | Very high | Low | Authoritative tool catalog; common result observer; bounded redaction and outcome rules | Implemented for 1.9.0 (unreleased) |
| 2 | One-document change ledger | Very high | Low–medium | Consistent mutation summaries; stable live-document identity; document-close callback | Implemented for 1.9.0 (unreleased) |
| 3 | Exportable work overview | High | Low | One-document ledger; structured result schema; bounded Markdown rendering | Implemented for 1.9.0 (unreleased) |
| 4 | Read-only hinting overview | High | Medium | Source hint/custom-parameter inventory; normalized PS and TT terminology | Directional |
| 5 | Hinting configuration linter | High | Medium | Read-only hinting overview; versioned rules and explicit severity model | Directional |
| 6 | Basic comparison of two open fonts | High | Medium | Stable document targeting; normalized high-level font, master, instance, glyph, feature, spacing, and kerning summaries | Directional |
| 7 | Versioned semantic font snapshots | Very high | High | Canonical bounded serialization; stable identities; schema versioning and fingerprints | Directional |
| 8 | Full semantic source comparison | Very high | High | Versioned semantic snapshots; field-aware comparison rules; bounded reporting | Directional |
| 9 | Automatic targeted pre/post snapshots | Very high | High | Semantic snapshots; mutation target adapters; retention and invalidation policy | Directional |
| 10 | Compiled-font regression comparison | High | High | Isolated export/build workflow; fontTools/Fontspector-style companion capabilities; reference artifact policy | Directional |
| 11 | Cross-source visual difference Reporter | High | High | Semantic source comparison; compatible layer mapping; native Reporter state and rendering | Directional |
| 12 | Controlled autohinter baseline | High | High | Reproducible build inputs; pinned autohinter versions/configuration; benchmark corpus | Directional |
| 13 | Rasterized hinting QA | Very high | Very high | Controlled baselines; rasterizer matrix; bounded image capture and comparison | Directional |
| 14 | Guarded PS and TT hint candidates | Very high | Very high | Hinting overview and linter; raster QA; detached candidate, review, approval, and verification contracts | Directional |
| 15 | General MCP-session rollback | High | Very high | Semantic snapshots; complete mutation coverage; conflict detection and explicit recovery policy | Directional |
| 16 | Multi-platform hinting benchmarks | High | Very high | Controlled baselines; raster QA; Windows/macOS engine infrastructure and reproducible fixtures | Directional |

## What 1.9 answers today

- **Checking agent work:** the panel and MCP tool show attributable mutation
  attempts, normalized outcomes, bounded targets and summaries, warnings,
  aggregate counts, save information, and retained chronological entries.
- **Comparing Glyphs sources:** the server can inspect explicit source facts
  through existing tools, but 1.9 does not yet produce a complete semantic or
  visual diff between sources. Items 6–11 describe that progression.
- **MCP versus direct source access:** MCP adds live Glyphs context, typed
  operations, safety metadata, confirmation boundaries, read-back results,
  and the 1.9 activity ledger. It does not by itself improve artistic
  judgement, and the ledger does not prove every semantic before/after value.
- **Hinting:** current generic APIs can inspect some source data, but Glyphs MCP
  does not yet claim to outperform a PS or TT autohinter. Items 4–5 add
  explainable source review; items 12–14 require reproducible baselines,
  raster evidence, and guarded candidates before such comparisons are useful.

## 1.9 boundaries

- One live `GSFont` is tracked per ledger session, even if several documents
  are open.
- Tracking starts on the first attributable MCP edit, save, or code operation
  whose result indicates an action or leaves the outcome uncertain. It resets
  on request, tracked-document close, or Glyphs quit.
- The ledger is process-local, capped at 256 retained events, and preserves
  aggregate counts for earlier omitted events.
- Read-only calls, UI-only calls, exports, previews, dry runs, and results that
  prove no mutation started do not appear in the change list. Failures remain
  visible only when a mutation may have started or its outcome is uncertain.
- Generic code operations are opaque. The ledger never stores arbitrary code,
  full outline payloads, or unrestricted arguments.
- Persistence, rollback, multi-document aggregation, semantic comparison,
  hinting recommendations, and raster QA remain outside this milestone.

For the larger guided review design that can consume future snapshots,
comparisons, and hinting evidence, see the
[AI font proofreading implementation plan](content/contributor/ai-font-proofreading-plan.mdx).
