---
name: glyphs-mcp-opentype-features
description: Inspect OpenType feature code, stylistic sets, character variants, prefixes, and classes in Glyphs; explain their scope without presenting the workflow as a general font-feature compiler or editor.
---

# Glyphs MCP OpenType features

Use this focused workflow for OpenType feature inspection and stylistic-set reporting.

## Core rules

- Resolve one explicit document with `list_open_fonts`; never use a legacy font index as authority.
- Prefer a typed OpenType inspection tool when the connected runtime exposes one.
- When no typed tool covers the inspection, use `execute_python` with `intendedEffect=read`, a concise reason, explicit document context, and bounded output.
- Search `docs_search` and fetch focused pages with `docs_get` before interpreting unfamiliar Glyphs feature APIs.
- Report feature tags, disabled/automatic state, source classes or prefixes, substitutions, contextual rules, and unsupported constructs separately.
- Do not mutate feature code, compile features, export, or save the font during inspection.
- Treat the old skill name `glyphs-mcp-features` as a documentation tombstone only; it is not a v2 skill alias.

## Workflow

1. Call `get_server_info` and `list_open_fonts`, then select the stable `documentId`.
2. Inspect features, classes, and prefixes through the narrowest typed operation available.
3. If fallback Python is needed, run read-intent code only and check `observedDocumentChange` plus `scopeViolations` in the result.
4. Group stylistic-set output by tag and name. Keep contextual or unsupported rules visible rather than guessing their expansion.
5. Report any read-intent violation as a safety finding and do not rerun the script as a mutation.

## Deeper references

- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
- [Safety model](https://github.com/thierryc/Glyphs-mcp/blob/main/content/concepts/safety-model.mdx)
- [Project briefing](https://github.com/thierryc/Glyphs-mcp/blob/main/CODEX.md)
