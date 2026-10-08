# Private lean v2 skill policy

Current scope is tracked in [2.0.2 candidate notes](../V2.0.2-RELEASE.md); the
[eighteen-tool contract](../content/reference/command-set.mdx) is the interface
reference. Shared skill contracts are [conversation edits](glyphs/references/edit-workflow.md),
[native scripts](glyphs/references/python-scripts.md) and
[Git checkpoints](glyphs/references/git-checkpoints.md). Focused skills link to
these rather than repeating the full authorization and recovery policies.

Skills target the current coordinated private build: bridge, sidecar and skills
are updated together. `$glyphs` identifies the specific connection and checks
its negotiated capabilities before routing a task. Missing required capabilities
mean the installation needs updating; do not maintain workflows for earlier
private v2 builds. V1 has separate instructions and is not changed by this policy.

The public interface contains eighteen tools: `get_status`, `list_documents`, `create_document`, `open_document`,
`read_entities`, `start_job`, `get_job`, `apply_job`, `accept_job`,
`discard_job`, `save_document`, `start_edit_workflow`, `get_edit_workflow` and
`respond_edit_workflow`, `import_document`, `activate_document`, `close_document` and `compare_fonts`.
There is no typed-prototype or alternate history interface. `python_script`
requires `script.native.v1` and uses direct native execution with a saved baseline.
Native script manifests have no fixed target-count ceiling. Complete requests
remain limited to 4 MiB; preparation and target revalidation yield between chunks.
Typed action, outline and read limits retain their separate contracts.
Original font-task authorization permits Run without mandatory code review or a
human click. Source remains optional Script details. Writing a script includes
review; write-only/review-only tasks do not execute. Explicit previews wait.
Retired modes, layer-content patches and script snapshot recovery are removed.

The [shared script route guide](glyphs/references/python-scripts.md#choose-the-route)
includes direct native bulk geometry, numeric spacing, approved kerning maps,
manual feature source, cross-master transforms and metadata edits. The default
route is the same at every target count. Typed algorithms,
read-only queries, compilation/export and plugin iteration retain their own
workflows. Saved reload recovers persisted whole-font data, clears Undo history
and discards later edits; it does not provide selective Undo or external recovery.

Use explicit bounded reads, including `selection.context.v1` for compact
selection counts and optional node evidence. Typed mutation jobs keep short guarded native writes and selective recovery.
Widths, Dimensions, glyph colors, exact kerning assignments and coordinate-only node updates can prepare
inside Glyphs on detached targets; other algorithms retain external preparation.
Typed and script results share Keep/Save, their appropriate recovery, and the
optional 30-second card countdown; explicit wait directives disable it.
Conversation guidance reuses known bindings and compact polling. Fully explicit
path targets skip unrelated selection reads while retaining exact geometry
guards. Card details are bound to workflow, document, job and request identity.
The negotiated `native_action` family is one closed `start_job` kind; it does
not expose arbitrary selectors, menu commands, Python or another MCP endpoint.
Closed `feature_compile` diagnostics and verified `font_export` artifacts use
the same start/poll lifecycle and capability negotiation without adding tools.
Support dirty reads without Save; report missing or incomplete evidence honestly.
A separately authorized native development task is not a fallback for an old
private installation and does not add a public MCP capability.

Canonical skills live in `skills/`; synchronize managed files to
`plugins/glyphs-mcp/skills/` with the existing script. Preserve invocation policies
and installer ownership/backups. Do not edit plugin caches. Validate routing,
requested fields, capability advertisement, packaged copies and the relevant
lean tests; require disposable native evidence for claims about Glyphs behavior.

- Beta 8 milestone 6: shared [Git checkpoint guidance](glyphs/references/git-checkpoints.md),
  opt-in project configuration, Save/checkpoint outcome separation, bounded history
  and historical restoration; native qualification tracked in the milestone report.

- Beta 8 milestone 8: [exact kerning assignments](glyphs/references/kerning-edits.md)
  and [language proofing](glyphs/references/kerning-proofing.md) share existing tools.
  Native assignments retain selective recovery; MIT pair provenance and bounded
  Unicode mapping remain independent of editing and collision analysis.
