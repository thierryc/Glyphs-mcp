---
name: glyphs-mcp-development
description: Use this skill to create, extend, or review reusable workspace-first Glyphs Python scripts and Python plug-ins, including general, reporter, filter, palette, select-tool, and file-format plug-ins, while grounding API and template choices in the bundled Glyphs documentation.
---

# Glyphs MCP development

Create workspace-first Glyphs scripts and plug-ins from pinned SDK templates.

## Core rules

- Search with `docs_search`, then fetch only the relevant pages with `docs_get` before using unfamiliar Glyphs APIs or plug-in lifecycle methods.
- Use `glyphs-mcp-scripting` instead when the request is to preview, run, or
  debug a one-off script inside the live Glyphs app. Bring verified behavior
  back here when it should become a reusable script or plug-in.
- Target Glyphs 3.5 and Glyphs 4 unless the user explicitly requests one version.
- Create files in the current workspace. Never write to a live Glyphs Scripts or Plugins folder without a separate explicit request.
- Never install, execute, reload, restart Glyphs, or overwrite an existing artifact automatically.
- Keep `Contents/MacOS/plugin` from the bundled SDK template unchanged and retain the bundled Apache 2.0 attribution.
- Validate after scaffolding and after source edits.
- When extending this repository's outline-candidate system, keep mathematics
  and process-local state free of GlyphsApp/AppKit imports; keep MCP wrappers
  responsible for snapshots and guarded mutation; keep Reporter callbacks
  drawing-only. Add every public tool to `TOOL_CATALOG`, then register it only
  with `glyphs_tool`; direct `mcp.tool` decorators are forbidden. Give it all
  four safety hints, one visibility/effect class, concise routing metadata, and
  an output schema when it belongs to a structured workflow. Import its module
  through `mcp_tools.py`, and export every Reporter principal class through both
  `plugin.py` and `Info.plist`.
- Keep the MCP surface lean. Prefer a dedicated typed tool over an opaque action
  multiplexer, but do not add a wrapper when an existing candidate adapter or
  lifecycle transition already expresses the same operation.
- For candidate, curve, spacing, or kerning tools, preserve legacy JSON text and
  add the validated structured-result envelope. Keep workflow details in typed
  `data`; do not expand the common envelope with domain-specific fields.

## Workflow

1. Determine whether the artifact is a standalone script or a Python plug-in. For plug-ins, choose `general`, `reporter`, `filter`, `palette`, `select-tool`, or `file-format`.
2. Resolve the human name, purpose, destination, and plug-in class/developer metadata. Use a workspace destination when none is specified.
3. Search the bundled docs for the APIs and plug-in base class involved. Fetch the scripting or template guide plus only the API pages needed.
4. Run `scripts/scaffold.py create` from this skill directory. It refuses existing outputs and live Glyphs installation folders by default.
5. Edit the generated Python for the requested behavior. Prefer documented GlyphsApp APIs and keep Glyphs 3.5/4 compatibility explicit.
6. For this repository, run the catalog, registration, routing, structured-result,
   single-surface startup, and mirror tests before broader release gates.
7. Run `scripts/scaffold.py validate <artifact> --target both`. Treat static validation as necessary but not equivalent to running inside Glyphs.
8. Report the created path, documentation consulted, validation result, compatibility notes, and any separate manual install or runtime test the user may choose.

## Scaffold helper

Create a script:

```text
python3 scripts/scaffold.py create script --name "My Script" --description "What it does" --destination .
```

Create a plug-in:

```text
python3 scripts/scaffold.py create reporter --name "My Reporter" --class-name MyReporter --developer "Your Name" --destination .
```

Validate an artifact:

```text
python3 scripts/scaffold.py validate "My Reporter.glyphsReporter" --target both
```

Use `--allow-live-install` only after the user explicitly asks to create directly in a Glyphs Scripts or Plugins folder. This flag does not install, reload, or execute the artifact.

## Documentation queries

- Scripts: `creating Glyphs scripts`, then the specific GlyphsApp class or method.
- Plug-in overview: `Glyphs Python plug-in templates` and `Glyphs plug-in API`.
- Plug-in types: `GeneralPlugin`, `ReporterPlugin`, `FilterWithoutDialog`, `PalettePlugin`, `SelectTool`, or `FileFormatPlugin`.

## Deeper references

- [Agent skills](https://github.com/thierryc/Glyphs-mcp/blob/main/content/concepts/agent-skills.mdx)
- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
- [Tool catalog](https://github.com/thierryc/Glyphs-mcp/blob/main/src/glyphs-mcp/Glyphs%20MCP.glyphsPlugin/Contents/Resources/tool_catalog.py)
- [Scaffold helper](https://github.com/thierryc/Glyphs-mcp/blob/main/skills/glyphs-mcp-development/scripts/scaffold.py)
