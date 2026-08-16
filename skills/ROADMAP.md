# Glyphs MCP Skills Roadmap

This document is the long-run implementation and maintenance plan for repo-local agent skills in Glyphs MCP.

## Goal

Ship a small, high-signal set of repo-owned skills that make common Glyphs MCP workflows safer, easier to discover, and more consistent across agents.

The shared package targets Codex/ChatGPT, Claude Code, Cursor, and GitHub
Copilot CLI through one canonical skill source.

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

## Existing vibe-coding skills to preserve

These capabilities predate the general live-scripting workflow and remain
authoritative in their own scope:

1. `glyphs-mcp-development` creates reusable workspace scripts and all six
   supported Python plug-in types from pinned templates.
2. `glyphs-mcp-outlines-docs` owns documentation-grounded live fallback code
   for outline work when dedicated tools are insufficient.
3. `glyphs` routes general Glyphs work and distinguishes focused workflows.
4. `glyphs-mcp-italic-first-pass` retains its narrowly guarded generated-Python
   fallback inside the italic construction workflow.

`glyphs-mcp-scripting` complements these skills; it does not replace them.

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

### 1. `glyphs`

Use when the task is about:

- starting a general Glyphs MCP task
- reading the current server, font, master, and selection context
- choosing the matching focused workflow
- recovering from a missing local connection

Core rules:

- start with `get_server_info` and `list_open_fonts` when context is unknown
- route focused tasks to the matching narrow skill
- prefer dedicated tools, reviews, and dry runs before mutation
- require explicit approval for confirm-gated actions
- never auto-save the font

Primary repo references:

- `content/getting-started/connect-client.mdx`
- `content/tutorial/first-session.mdx`

### 2. `glyphs-mcp-kerning`

Use when the task is about:

- kerning collisions
- kerning bumper reviews
- deterministic kerning exception application

Core rules:

- use Edit for the specialized workflow; keep review calls non-mutating
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

- use Edit for the specialized workflow; keep review calls non-mutating
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

### 5. `glyphs-mcp-italic-first-pass`

Use when the task is about:

- creating a first-pass italic or oblique from roman glyphs
- copying all glyphs, selected glyphs, named glyphs, or the current glyph to an italic master
- checking Cursivy stem prerequisites before slanting

Core rules:

- use Read-only for detached candidate preview and Edit for materialization,
  acceptance, or the legacy direct review/apply workflow
- read current font/master/selection first
- run `review_master_stem_metrics` before Cursivy
- start with `preview_italic_first_pass_candidate`
- review the candidate session, dry-run acceptance, obtain approval, then confirm acceptance
- only mutate with explicit approval and `confirm=true`
- never auto-save the font

### 6. `glyphs-mcp-icon-font`

Use for stable Unicode and PUA assignment workflows in icon or symbol fonts.
Review before allocation, require a previous map for released fonts, preserve
existing assignments, dry-run before applying, and delegate drawing or metrics
work to the existing specialized skills.

### 7. `glyphs-mcp-development`

Use when the task is about:

- creating or reviewing standalone Glyphs Python scripts
- scaffolding general, reporter, filter, palette, select-tool, or file-format plug-ins
- grounding Glyphs development work in the bundled Handbook, API, and SDK templates

Core rules:

- search with `docs_search`, then fetch focused pages with `docs_get`
- generate into the current workspace from pinned SDK assets
- validate Python syntax, bundle metadata, principal class, and placeholders
- never overwrite, install, execute, reload, or restart automatically
- target Glyphs 3.5 and Glyphs 4 unless the user requests one version

### 8. `glyphs-mcp-features`

Use for OpenType feature inspection and stylistic-set glyph groups with Glyphs
links. Keep it focused on the existing typed feature tools.

### 9. `glyphs-mcp-litsquare-metadata`

Use for LitSquare metadata, inherited settings, semantic path roles, and
layer-specific IconGrid centering. Keep its guarded patch and verification
contracts intact.

### 10. `glyphs-mcp-release`

Use for coordinated versioning, documentation, packaging, release validation,
signing, notarization, and publication gates. External release actions remain
separate approvals.

### 11. `glyphs-mcp-scripting`

Use when the task is about:

- vibe coding or debugging a focused Python idea in the running Glyphs app
- Macro Panel snippets and read-only live probes
- testing an idea before turning it into a reusable script or plug-in

Core rules:

- inspect live context and prefer dedicated tools or domain skills first
- ground unfamiliar APIs with `docs_search` followed by focused `docs_get`
- use `execute_code_with_context` for glyph/layer work and `execute_code` for
  broader scripts
- preview mutations and external side effects with `snippet_only=true`, show
  the exact code and target, and stop for approval
- execute only unchanged approved code and verify through dedicated reads
- never save, install, reload, restart, access files or the network, or launch
  subprocesses without separate authorization
- hand reusable artifacts to `glyphs-mcp-development`

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

The executable prompt/expected-result matrix lives in
`src/glyphs-mcp/tests/fixtures/llm_skill_routing.json`; keep these roadmap
examples aligned with that canonical evaluation fixture.

- "Help me connect Codex to Glyphs MCP and verify it works."
- "Review kerning collisions and only apply approved bumper fixes."
- "Review spacing for the selected glyphs and do a dry run first."
- "Create a documented Glyphs reporter plug-in in this workspace."
- "Inspect selected nodes, edit outlines safely, and look up the relevant Glyphs docs."
- "Create a first-pass italic for selected glyphs, checking Cursivy stems and doing a dry run first."
- "Run a read-only live script that reports the selected Glyphs layers."
- "Preview a script that changes the selected layer width, but do not run it until I approve the exact code."
- "Create a reusable Glyphs Script-menu Python file in this workspace."
- "Create a Glyphs Reporter plug-in in this workspace."

### Negative checks

Make sure these do not over-trigger unrelated skills:

- generic Python packaging questions
- generic Python requests with no Glyphs app or font target
- release engineering tasks
- installer-only tasks
- broad docs-site edits

### Regression checks

- No MCP tool changes
- Installer behavior remains the same apart from managing the eleventh skill
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

- a host changes its plug-in or skill distribution contract
- Claude-native distribution constraints matter directly
- the skill set expands enough that shared references or scripts need their own architecture
