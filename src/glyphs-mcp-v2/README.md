# Glyphs MCP 2.0

V2 is a non-public hard reset. It has no compatibility aliases, transition
wrappers, or workflow-specific mutation endpoints. V1 and Glyphs 3 remain
unchanged.

## Directive

Glyphs MCP separates three kinds of responsibility:

1. **Knowledge supplies evidence.** The packaged offline corpus contains
   pinned, searchable, version-aware, cited information about type design,
   font engineering, Glyphs APIs, scripting, plug-in development, and file
   formats.
2. **Skills supply expertise.** Skills interpret evidence, make typographic
   judgments, choose workflows and calculations, handle exceptions, design
   proofs, and decide when Python is the appropriate fallback.
3. **Tools supply mechanics.** Tools read canonical state, compute declared
   observations, evaluate constraints, create immutable previews, apply exact
   stored patches, verify results, maintain history, and expose effect
   boundaries.

The design rule is **permissive expression with strict structural integrity**.
Tools do not embed spacing taste, category heuristics, or hidden preservation
choices. They do reject stale fingerprints, ambiguous identities, invalid
ownership, unsupported replay, incomplete read-back, and unverified writes.

There are three independent fingerprint domains. A live canonical document
fingerprint controls preview/apply staleness. A source-file fingerprint
identifies the current working file bytes. A destination-file fingerprint
protects Save As or export overwrite. Never substitute one for another.

## Public contract

The catalog contains exactly 18 tools:

- discovery: `get_server_info`, `list_documents`, `read_document`
- constraints: `evaluate_constraints`
- changes: `preview_change`, `apply_change`
- history: `get_operation`, `list_history`, `revert_change`
- Knowledge: `search_knowledge`, `get_knowledge`
- permanent fallback: `execute_python`
- persistence/export: `preview_export`, `apply_export`, `save_document`
- host/runtime: `open_document_view`, `get_runtime_status`, `repair_runtime`

The generated command reference is
[`content/reference/command-set-v2.mdx`](../../content/reference/command-set-v2.mdx).
MCP discovery is the source of truth for request schemas.

`get_server_info.data.runtimeIdentity` identifies the code actually loaded by
Glyphs. Check its full `codeHash` or compact `runtimeId` after restarting the
app; the semantic `serverVersion` remains `2.0.0` across private hard-reset
builds and is not sufficient to prove that a new payload loaded.

`save_document` is the only working-source persistence boundary. It supports a
verified normal save or explicit Save As and requires current fingerprints and
confirmation. Existing destinations fail closed unless
`overwritePolicy=replace_if_match` carries the matching destination
fingerprint.

Native Glyphs Save remains available at all times, including while a verified
transaction is active. A save-only event does not stale an immutable preview
and is never converted into a permanent runtime incident. The runtime records
a per-document save epoch and evidence ledger, then reconciles a verified live
result as saved-before, saved-after, saved-intermediate, or unclassified source
drift. An intermediate save rebases history to the residual semantic diff.
Verification failure rolls back only the live document; it never rewrites or
auto-saves the source file.

## Shared mechanical model

`EntitySelector` addresses canonical entity kinds by exact IDs, closed filters,
or a compact Boolean predicate AST, with parent relations, typed deterministic
ordering, and fingerprint-bound pagination. It includes first-class nodes as
well as layers, shapes, and anchors. `Projection` can compute named generic
reducers over the complete selected set. Mutation selectors are resolved to
exact canonical paths during preview.

`Projection` requests canonical fields or registry-backed observations. Every
observation reports provenance and completeness. Current observations include
bounds, geometry counts, ownership, alignment, metrics inheritance, grid,
horizontal and vertical spacing, effective metadata, and detached compilation
diagnostics.

`Constraint` is the same assertion language for standalone evaluation,
preconditions, postconditions, and read-back verification. Constraints compare
literals, exact references, or current fields. They never choose an operation.

`ChangeOperation` contains only `set`, `translate`, `insert`, `remove`, `move`,
and `duplicate`. Coordinate quantization is explicit (`exact` or `grid`).
Translation uses one registry for layer, shape, node, and anchor targets;
locks and alignment modes remain unchanged while detached native execution and
exact read-back determine feasibility.
Ownership-sensitive master and layer membership uses a private structural
registry because Glyphs owns master layers with their master and reserves the
master-layer prefix. This registry enforces structure; it does not contain a
workflow solver.

## Immutable preview and verified apply

`preview_change` binds normalized operations to:

- exact resolved targets;
- the base live-document fingerprint;
- schema and runtime dependencies;
- before/after constraint evidence;
- the semantic patch and proposed fingerprint;
- warnings and blockers.

`apply_change` consumes that stored patch. It does not rerun planning or code.
Every live document write passes through snapshot, detached simulation, apply,
complete read-back, verification, rollback on failure, audit, and history.
Verified changes normally leave the font unsaved; a concurrent native save may
persist the input, output, or an intermediate state and is reported explicitly.
`revert_change` performs a
conflict-aware inverse against the current document instead of overwriting
later unrelated edits.

## Permanent Python fallback

`execute_python` is a permanent architectural capability, even as declarative
coverage grows:

- Before generating detached code, inspect
  `get_server_info.data.registries.pythonExecution.detachedNamespace`. It
  publishes the reviewed Python 3.14 built-ins, import roots, injected context,
  available constructors, explicit denials, and a contract fingerprint.

- `read_only` performs bounded inspection on a detached document and proves
  that the live canonical fingerprint and dirty state did not change.
- `staged_document` runs against a detached document and returns the same
  immutable preview lifecycle as declarative operations. Confirmation occurs
  through `apply_change`; the code is never rerun.
- `live_open_world` is the last-resort boundary for unsupported Glyphs APIs,
  UI, files, processes, or other external effects. It requires explicit
  confirmation and reports verified document effects separately from
  unverifiable external effects, checkpoints, and recovery evidence.

Skills prefer declarative operations when they fit because they are easier to
inspect and reverse. They use Python whenever the typed mechanics cannot
express the task. Python is not deprecated and must not be removed.
Detached execution is not described as a security sandbox: its safety boundary
is the discarded clone plus exact preview/application verification. Structured
errors distinguish unavailable symbols and imports, script-rejected candidates,
and unclassified host failures while proving the live fingerprint and dirty
state whenever execution fails.

## Knowledge builds

The runtime Knowledge corpus is offline. Entries include stable IDs, topics,
Glyphs version applicability, authority class, source URL, verification date,
checksum, citations, and focused coding examples. Search ranking and
pagination are deterministic.

Create the isolated v2 development environment once from repository root:

```bash
python3.14 -m venv .venv-v2
.venv-v2/bin/python -m pip install -r requirements-dev.txt
```

Build or verify it from repository root:

```bash
.venv-v2/bin/python scripts/build_v2_knowledge.py
.venv-v2/bin/python scripts/build_v2_knowledge.py --check
```

Upstream sources are reviewed and pinned during builds. Runtime search never
fetches uncontrolled network content.

## Qualification

Run the isolated v2 suite and deterministic generation checks:

```bash
.venv-v2/bin/python -m pytest -q src/glyphs-mcp/tests/test_v2_*.py
.venv-v2/bin/python scripts/audit_canonical_schema.py --repo-root .
.venv-v2/bin/python scripts/build_v2_knowledge.py --check
.venv-v2/bin/python scripts/render_v2_command_reference.py --check
scripts/sync_codex_plugin_skills.sh --check
.venv-v2/bin/python scripts/build_v2_runtime_payload.py
git diff --check
```

Glyphs 4 disposable-font qualification is exposed through generic gates:

- `verify_open_document_view`
- `verify_copy_and_make_copy`
- `verify_generic_change_lifecycle`
- `verify_generic_kerning_lifecycle`
- `verify_staged_python_preview_lifecycle`

The gates refuse non-disposable fonts, never save, and require exact baseline
restoration. Exported font quality, shaping, and typographic acceptance remain
skill-guided review tasks rather than tool-side policy.
