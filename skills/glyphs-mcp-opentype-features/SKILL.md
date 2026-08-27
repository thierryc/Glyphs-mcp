---
name: glyphs-mcp-opentype-features
description: Inspect OpenType feature code, stylistic sets, character variants, prefixes, and classes in Glyphs; when explicitly requested, change their ordered collections through the verified apply-first v2 mutation contract.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP OpenType features

Use this focused workflow for OpenType feature inspection and stylistic-set reporting.

## Core rules

- Resolve one explicit document with `list_open_fonts`; never use a legacy font index as authority.
- Use `list_opentype_items` for ordered feature, class, and prefix inspection,
  including parsed stylistic-set substitutions and unsupported-rule warnings.
- When no typed tool covers the inspection, use `execute_python` with `intendedEffect=read`, a concise reason, explicit document context, and bounded output.
- Consult the bundled Glyphs documentation before interpreting unfamiliar
  feature APIs.
- Report feature tags, disabled/automatic state, source classes or prefixes, substitutions, contextual rules, and unsupported constructs separately.
- Do not mutate feature code, compile features, export, or save the font during inspection.
- When compilation is explicitly requested, call
  `compile_opentype_features` with documentId and expectedDocumentFingerprint. It
  preflights `compileFeatures()` on one detached copy before compiling live and
  must report unchanged canonical state and source bytes. It never calls
  `updateFeatures()`, generates source, or saves.
- When the user explicitly requests an edit, use `apply_opentype_updates` with
  one stable document ID, the current fingerprint, explicit `create`, `update`,
  `move`, or `delete` actions, unique kind/name targets, and a reason. Creation
  and move may include an explicit collection index. Rename remains an explicit
  delete/create operation so entity identity is never changed implicitly.
- Custom code requires the resulting `automatic` state to be false. The typed
  mutation applies immediately, verifies detached and live canonical state,
  records one audit/change operation, never compiles, and never saves.
- Do not use the removed glyphs-mcp-features or list_style_sets workflow in
  v2; `list_opentype_items` replaces that inspection surface.

## Workflow

1. Call `get_server_info` and `list_open_fonts`, then select the stable `documentId`.
2. Inspect features, classes, and prefixes with `list_opentype_items`.
3. If fallback Python is needed, run read-intent code only and check `observedDocumentChange` plus `scopeViolations` in the result.
4. Group stylistic-set output by tag and name. Keep contextual or unsupported rules visible rather than guessing their expansion.
5. Report any read-intent violation as a safety finding and do not rerun the script as a mutation.

For an explicit edit, re-read the document fingerprint immediately before the
single `apply_opentype_updates` call. Report its operation ID and revert
availability; do not add a second approval or review-token flow.

## Deeper references

- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
- [Safety model](https://github.com/thierryc/Glyphs-mcp/blob/main/content/concepts/safety-model.mdx)
- [Project briefing](https://github.com/thierryc/Glyphs-mcp/blob/main/CODEX.md)
