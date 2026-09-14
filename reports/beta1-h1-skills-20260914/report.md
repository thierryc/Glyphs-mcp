# H1 — retire incompatible private skills

**Implemented and installed for the configured Codex skill directory. Stop here
for user feedback; H2 has not started.**

The seven obsolete private audit families no longer exist under
`/Users/thierryc/.codex/skills`. Eleven current lean skills match the candidate
payload exactly. The sidecar and bridge are unchanged. This is a skill/setup
qualification, not a new font-operation or latency benchmark.

## What changed and why

The existing `AgentSkillBundleInstaller` now recognizes the seven removed
families only when installing a lean entry, when that family is absent from the
incoming manifest, and when the installed contents identify the retired private
`apiMajor == 2` workflow. A name alone does not qualify a folder. Matching v1,
current lean, unrelated and still-shipped skills remain untouched.

A matching current ledger hash permits automatic retirement. Unowned or edited
folders remain `preserved-conflict`, with their exact path and the existing
**Replace preserved skills (backup)** action. Explicit replacement archives
recognized retired folders and reports `retired` plus the backup path. Backups
use the existing sibling directory outside discovery and contain restoration
coordinates and the complete content identity. A failed retirement/ledger write
restores the just-retired folders from those backups; this is not a new general
installer recovery system.

The entry gains one routing-table row. Details live in
[specialized scope](../../skills/glyphs/references/specialized-scope.md).
For example, “audit this icon font” now distinguishes a bounded metadata check
from a full audit requiring separately scoped native/offline work. An obsolete
skill's gate is not evidence that an up-to-date lean runtime needs upgrading.
Missing capabilities required by a current supported private workflow still
require a coordinated installation update. No older-private fallback is added.

## Installation evidence

All seven actual folders had old owner markers but no current ownership hashes.
They were therefore **not treated as automatically owned**. H1's explicitly
reviewed cleanup used the existing replacement action after checking their
complete fingerprints and all eleven incoming destinations. The seven folders
matched the older instruction content; the compared source/cache copies only
added an interface-routing paragraph to their entries. No unexplained reference
or invocation-file differences were found.

[Installation](installation.json) records one updated entry, ten current skills,
seven retirements, seven exact verified backups, and zero remaining conflicts in
the managed installation. A second verification run reported eleven `current`
entries and made no backup changes. [Log](installation.log),
[reviewed identities](reviewed-retirements.json), and
[pre-install file identities](installed-before.json) preserve the evidence.
The driver [InstallSkills.swift](InstallSkills.swift) calls the existing public
installer; it is qualification code, not a shipped skill-management service.

| Check | Result |
|---|---|
| Installer regression class | **130 passed**, zero failures; includes seven new H1 tests |
| Focused Python checks | **46 passed**, one optional Copilot test skipped |
| Managed retirement | All seven families, exact nested files and owner markers backed up |
| Ownership/conflicts | User edits and marker-only/unowned folders preserved by default |
| Explicit replacement and repeat | Exact backups, correct outcomes, second no-op |
| v1 and unrelated skills | Same-name v1, lean instructions, still-shipped families and v1 payload preserved |
| Failure controls | Backup failure preserves original; immutable-ledger failure restores exact retired contents |
| Routing review | Eight agent dry-run cases passed; not a fresh v1/native benchmark |
| Packaging | Eleven synchronized skills, valid entry metadata, payload validation passed |
| Runtime | Seven tools, five jobs, unchanged live identities; no runtime installation or restart |

[Test results](test-results.json) and [routing review](routing-review.json)
separate assertions from agent interpretation. Installer execution took 12.131
seconds for the final class run; Python execution took 4.20 seconds. These are
test-suite durations, not MCP latency or native callback measurements.

First-attempt friction is retained: sandboxed Xcode asset compilation failed
before tests; the authorized retry built successfully. One new Python assertion
was too sensitive to indentation and was normalized. One new Swift failure
simulation assumed a directory could not be atomically replaced; macOS allowed
it. The corrected immutable-file simulation passed exact restoration.

The broad Swift run also found an **unrelated existing Starter assertion** at
`DesktopProjectTests.swift:18`: it expects the contiguous phrase
`get_status and list_documents`, while the unchanged template now instructs
one discovery followed by ID reuse. It remains logged and unfixed in H1. Do not
interpret the focused pass as a clean full desktop suite. Reconcile this obsolete
assertion when reviewing setup documentation in H2.

## Preservation and limits

[Verification](verification.json) checked 3,605 existing source files, 1,695
unrelated installed skill files, and 38 files in the seven corresponding outer
source/cache families. Only the intended H1 source files changed. v1 source and
runtime implementations remain unchanged. No document was discovered, edited,
saved or reopened by this task. No native mutation call was made.

The [before](runtime-before.json) and [after](runtime-after.json) observations
agree: sidecar `2.0.0-beta.1+82daa62ac227`, bridge
`2.0.0-beta.1+8b74a8d27ae4`, Glyphs 4.1 (4107), installer build 43. Full component
hashes and release metadata are preserved in those records.

Plugin caches and the outer research worktree were deliberately not modified.
This already-running task's skill catalog still contains their historical entries.
**Managed on-disk cleanup does not prove every client cache has refreshed.** A
fresh discovery session must choose the current installed entry; when another
source supplies an old skill, report that precise path. No hot-refresh claim is
made. The installed desktop application's broad replacement notice also still
uses old “beside their original paths” wording; the installer log and new result
supply the accurate sibling backup paths. That notice belongs in H2's setup copy
review, not a second backup mechanism.

The source sits on pre-existing uncommitted desktop changes. The [scoped H1 source patch](installer-source.patch.gz)
is saved with its base fingerprints in this record; those underlying
installer changes have not been swept into an unrelated bulk commit. This is not
an independently signed or published installer release.

## Judgment and next fix

The change is useful: it removes seven misleading selectable instructions from
the managed directory while protecting edits and v1. Ordinary work adds no tool
call or document discovery. Specialized guidance loads only when needed. It
improves route accuracy; it does not implement the omitted audit families.
No speed improvement, token savings or new agent score is claimed.

**Next, after feedback: H2 — make migration, version and setup guidance agree with
the current candidate.** Example: “Which interface did I install?” should receive
one consistent answer, including the correct skill count and backup location.
