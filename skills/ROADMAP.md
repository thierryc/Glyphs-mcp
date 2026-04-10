# Glyphs MCP Skills Roadmap

This document is the long-run implementation and maintenance plan for repo-local agent skills in Glyphs MCP.

## Goal

Ship a small, high-signal set of repo-owned skills that make common Glyphs MCP workflows safer, easier to discover, and more consistent across agents.

The initial target is Codex and Claude Code, but the structure should stay compatible with the broader agent-skills model used by OpenAI and Anthropic.

## Research summary

### OpenAI

- OpenAI defines a skill as a folder with `SKILL.md` plus optional `references/`, `scripts/`, `assets/`, and `agents/openai.yaml`.
- OpenAI emphasizes progressive disclosure: the skill `name` and `description` are always available, while the body and bundled files are only loaded when relevant.
- OpenAI recommends keeping skills focused, using instructions by default, and only adding scripts or references when the workflow genuinely needs them.
- OpenAI also frames skills plus MCP as a complementary pair: the skill defines the workflow, and MCP provides the external tools.

Primary references:
- https://developers.openai.com/codex/skills/
- https://developers.openai.com/codex/concepts/customization/

### Anthropic

- Anthropic describes skills with the same basic pattern: folders of instructions, scripts, and resources that agents can discover dynamically.
- Anthropic also emphasizes progressive disclosure, code as an optional deterministic layer, and evaluation-driven iteration from real tasks rather than speculative design.
- Security guidance is similar: only install or trust skills you can inspect.

Primary references:
- https://www.anthropic.com/news/skills
- https://claude.com/blog/equipping-agents-for-the-real-world-with-agent-skills

### Local repo pattern

The local structural starting point is the `figma-use` skill bundled with the Figma plugin cache. The important design traits to copy are:

- a tight `SKILL.md`
- hard guardrails before workflow steps
- deeper detail pushed out of the core skill body
- explicit trigger language

The Glyphs skills should stay much smaller than `figma-use` until real usage justifies more depth.

## Architecture decision

### Source of truth

- Author the real skills in `./skills/`, as requested.
- Keep `./skills/` human-readable and repo-owned.

### Discovery bridges

OpenAI's repo auto-discovery documentation points Codex at `.agents/skills`, not bare `./skills/`.

Claude Code repo-local discovery should be exposed through `.claude/skills`.

To satisfy both constraints:

- keep authored skills in `skills/`
- expose them through `.agents/skills`
- expose them through `.claude/skills`
- prefer a symlink bridge so there is only one authored copy

This avoids duplicated skill folders and keeps updates simple.

## V1 skill catalog

### 1. `glyphs-mcp-connect`

Use when the task is about:

- starting the server
- choosing the right tool profile
- connecting Codex to the local endpoint
- running a first health check

Core rules:

- use the local endpoint `http://127.0.0.1:9680/mcp/`
- prefer a narrower Glyphs tool profile before connecting
- use `codex mcp add` and `codex mcp list`
- verify with `list_open_fonts`

Primary repo references:

- `content/getting-started/connect-client.mdx`
- `content/tutorial/first-session.mdx`

### 2. `glyphs-mcp-kerning`

Use when the task is about:

- kerning collisions
- kerning bumper reviews
- deterministic kerning exception application

Core rules:

- prefer the Kerning profile
- read current state first
- run `review_kerning_bumper` before any apply step
- always run `apply_kerning_bumper` with `dry_run=true` first
- only mutate with explicit approval and `confirm=true`
- never auto-save the font

### 3. `glyphs-mcp-spacing`

Use when the task is about:

- spacing review
- sidebearing and width suggestions
- guarded spacing application

Core rules:

- prefer the Spacing profile
- inspect current font/master/selection first
- run `review_spacing` before any apply step
- always run `apply_spacing` with `dry_run=true` first
- only mutate with explicit approval
- mention `set_spacing_params` and `set_spacing_guides` only as optional helpers
- never auto-save the font

### 4. `glyphs-mcp-outlines-docs`

Use when the task is about:

- outlines and path edits
- components and anchors
- selected nodes
- Glyphs docs lookup while editing

Core rules:

- prefer dedicated tools first
- use `execute_code_with_context` only for multi-step glyph-scoped work that is awkward with dedicated tools
- use `docs_search` and `docs_get` instead of loading broad docs
- re-read affected glyph state after mutations
- never auto-save the font

## Phase 2 candidates

These should only be added after repeated demand:

- `glyphs-mcp-editing`
- `glyphs-mcp-export`
- `glyphs-mcp-compensated-tuning`

## Authoring rules

- Keep each `SKILL.md` focused on one job.
- Prefer instructions over scripts unless determinism is clearly worth the extra maintenance.
- Use existing repo docs before inventing skill-local reference files.
- Keep the skill body short and procedural.
- If a workflow grows large, split the deep details into per-skill `references/` files.
- Default to review-first, dry-run-first instructions for mutating Glyphs workflows.

## Validation plan

### Structural checks

- Every skill folder contains `SKILL.md` and `agents/openai.yaml`.
- Every `SKILL.md` has `name` and `description` frontmatter.
- Every `openai.yaml` has matching display metadata and a skill-specific default prompt.

### Discovery checks

- Codex launched from the repo root sees the skills through `.agents/skills`.
- Claude Code launched from the repo root sees the skills through `.claude/skills`.
- Both bridges point to `skills/` rather than to duplicate copies.

### Trigger checks

Use these prompts as smoke tests:

- "Help me connect Codex to Glyphs MCP and verify it works."
- "Review kerning collisions and only apply approved bumper fixes."
- "Review spacing for the selected glyphs and do a dry run first."
- "Inspect selected nodes, edit outlines safely, and look up the relevant Glyphs docs."

### Negative checks

Make sure these do not over-trigger unrelated skills:

- generic Python packaging questions
- release engineering tasks
- installer-only tasks
- broad docs-site edits

### Regression checks

- No MCP tool changes
- No installer behavior changes
- No packaged plug-in runtime changes
- Repo diff stays limited to `skills/`, `.agents/skills`, `.claude/skills`, docs-site content, docs navigation, `README.md`, `CODEX.md`, and ignore rules

## Maintenance checklist

When a matching Glyphs MCP workflow changes:

1. Update the relevant `SKILL.md`
2. Update `agents/openai.yaml` if the trigger description or prompt should change
3. Re-run the structural and trigger checks
4. Keep the roadmap accurate if the skill catalog changes

## Deeper research policy

This roadmap already includes enough external guidance to ship v1.

Do more internet research only when one of these becomes true:

- the repo starts distributing skills as a plugin rather than as repo-local assets
- Claude-native distribution constraints matter directly
- the skill set expands enough that shared references or scripts need their own architecture
