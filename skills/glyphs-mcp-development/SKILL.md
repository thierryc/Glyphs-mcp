---
name: glyphs-mcp-development
description: Create, test and iterate native Glyphs 4 scripts and plugins in a workspace, including vibe coding and debugging existing plugins.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs Vibe Coding

Start with the user's idea, existing artifact and workspace. Choose a script for
a one-off action or a plugin for reusable native UI/behavior. Glyphs may be
closed: code creation, documentation lookup and static validation require no
MCP connection, document discovery or font Save. Ordinary font-design work
belongs to [$glyphs](../glyphs/SKILL.md); one-off native scripts can use
[scripting](../glyphs-mcp-scripting/SKILL.md).

Continue with the workspace, verified connection/document binding and relevant
instructions already in context. Load only a needed reference or missing excerpt;
switching between coding and font work does not restart either workflow.

## Create and revise

1. Resolve purpose, workspace, name, class and developer from the task or
   existing project. Choose `reporter` for an Edit View overlay. Other existing
   templates: `general`, `filter`, `palette`, `select-tool`, `file-format`.
   This skill and its scaffolder target Glyphs 4 only.
2. Search the [complete offline SDK/API and handbook corpus](references/development-docs.md)
   for unfamiliar APIs or missing evidence. Reuse loaded guides and native-symbol
   excerpts from the same installed corpus; fetch only what is needed next.
3. Run the existing helper from this skill directory, or resolve its absolute path:

   ```text
   python3 scripts/scaffold.py create reporter --name "Selection Lens" --class-name SelectionLens --developer "Project Developer" --destination /absolute/workspace --target 4
   python3 scripts/scaffold.py validate "/absolute/workspace/Selection Lens.glyphsReporter" --target 4
   ```

   For a script use `create script --name "My Script" --description "Purpose"`.
   Existing outputs are preserved. Revise an existing artifact in place within
   scope instead of rerunning create over it.
4. Implement the requested revision, keeping the SDK loader and Apache attribution.
   Validate changed artifacts; `runtimeTested: false` is not native qualification.
   Keep drawing callbacks free of file/network access, full-font traversal and
   font mutation. Batch related edits before validation and native installation.
5. Follow the [native install, verify and iterate loop](references/native-iteration.md)
   for authorised tests. Reuse the user's authorisation; preserve a working
   revision and compare workspace, installed and loaded evidence before taking
   the next action. Unchanged installed/loaded code needs no reinstall or relaunch.
   Use the [verification record and recovery guidance](references/verification-and-recovery.md)
   when verifying a revision, diagnosing a failure or resuming interrupted work.
   Generated files alone are not a working plugin; report the tested revision
   and relevant evidence.

## Live context, only when needed

For MCP access, reuse the specific [$glyphs](../glyphs/SKILL.md) connection and
intended document ID. Only missing or invalid bindings need
[document targeting](../glyphs/references/document-targeting.md). Reads are fresh;
dirty fonts need no Save. Native relaunch invalidates old document IDs.

The seven-tool MCP has no arbitrary Python execution or plugin reload tool.
Native development through files/UI does not add an MCP capability. A required
missing private capability needs the bridge, sidecar and skills updated together.
No earlier-private fallback or whole-font recovery is promised. Installation,
execution, restart, font edits and Save follow the user's authorised scope.
