# Verify a connection when needed

Inspect the tool catalog of the **specific MCP connection** when this connection has not yet been verified, before its first server call. Keep the connection identifier and
configured endpoint with the result; never merge catalogs from simultaneous
connections or infer an interface from the host app name or skill location.

- Exactly `get_status`, `list_documents`, `read_entities`, `start_job`, `get_job`,
  `apply_job`, `discard_job`: call that connection’s `get_status`. Use this lean
  workflow when `interface` is `glyphs-mcp-sidecar` and `interfaceVersion` is `1`.
  A private sidecar missing current interface/identity fields needs updating;
  do not route an earlier private build into a substitute workflow.
  An explicit different interface/revision requires its matching instructions.
- A v1 catalog with `get_server_info` and `list_open_fonts`: call that connection’s
  `get_server_info` and verify v1 identity. Select an available v1 entry/focused
  skill by its actual contents. The desktop payload includes `skills-v1/glyphs`.
  If unavailable, report “v1 server reachable; matching v1 skills unavailable”
  with the selected skill path and installation repair action. Do not apply lean
  job instructions to v1. Neither v1 nor the lean sidecar requires `apiMajor == 2`.
- Unknown or conflicting catalog/identity: report the observed connection,
  catalog and identity and request matching instructions. Do not invent tools.

Product `release.releaseVersion` (for example `2.0.0-beta.1`) and installer build
identify the release. `interfaceVersion: 1` identifies the lean tool contract;
`protocol: 1` is the sidecar/bridge wire contract; the dated MCP transport version
is negotiated separately. These numbers need not match. `sidecarVersion` and
`bridgeVersion` are numeric product versions in current builds. `runtimeId` and
`codeHash` identify each component’s initialization-time file fingerprint, not
its in-memory code. Missing fields are unavailable evidence, never a verified match; repair the
private installation before using workflows that require them. Compare sidecar and bridge independently against their own
expected receipt fingerprints; their hashes normally differ.

For a private lean workflow, check its required tools, negotiated
`readCapabilities` and `jobKinds` against the verified status already in context.
This does not require another status request for each read or skill switch. If a required capability
or supported job is missing, explain that the installation needs updating:
update the bridge, sidecar and skills together through the existing installer,
reload the affected processes, and verify fresh status. Do not maintain fallback
workflows for earlier private v2 builds, emulate missing features with another
job or script, or silently weaken evidence requirements. An operation outside
the current build's supported scope remains unsupported; an authorized separate
native development task does not establish that the MCP supports it.


Retain these results for this connection and endpoint during the task. Refresh
catalog/status after an endpoint change, component update, known process restart,
or evidence that contradicts the recorded interface/capabilities. Refresh status
when current health or installation verification is requested. A follow-up or a
focused-skill switch alone does not require either call. A transport reconnect
alone does not prove a Glyphs restart; stale document reads still fail explicitly.
Use [document targeting](document-targeting.md) for document lifetime and intent.

A focused file requiring `apiMajor == 2`, `read_document` or `execute_python`
targets the retired typed interface when requested as a required workflow. Report its exact path; select the matching
shipped lean skill or the entry's supported read reference. Repair a preserved
conflict through **Replace preserved skills (backup)** in the existing installer.
If the retired family has no current replacement, use [specialized scope](specialized-scope.md);
do not treat its obsolete version gate as evidence of a stale runtime.
Do not infer compatibility from a name or `surface` label. For failed setup,
use [connection troubleshooting](connection-troubleshooting.md).
