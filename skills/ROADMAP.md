# Private lean v2 skill policy

Skills target the current coordinated private build: bridge, sidecar and skills
are updated together. `$glyphs` identifies the specific connection and checks
its negotiated capabilities before routing a task. Missing required capabilities
mean the installation needs updating; do not maintain workflows for earlier
private v2 builds. V1 has separate instructions and is not changed by this policy.

The public interface remains twelve tools: `get_status`, `list_documents`,
`read_entities`, `start_job`, `get_job`, `apply_job`, `accept_job`,
`discard_job`, `save_document`, `start_edit_workflow`, `get_edit_workflow` and
`respond_edit_workflow`.
There is no typed-prototype, live Python or alternate history interface.

Use explicit bounded reads, including `selection.context.v1` for compact
selection counts and optional node evidence. Native jobs use external
preparation, short native writes and the existing Undo/discard mechanisms.
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
