# Source-bound typed-export instance IDs — 2026-10-27

Typed export previously required a live GSInstance ID to exist verbatim in the
saved source. After LeftyNote's native recovery, its clean live font had regenerated
instance IDs while its saved package retained the original IDs. Exact IDs returned
by `read_entities` therefore failed in the external export worker.

The sidecar now captures the complete bounded, ordered instance inventory using
exact live selectors after snapshot creation. It checks the clean document binding,
generation and saved-source hash before and after those reads. Private evidence is
passed separately from the public request. The worker validates that source hash,
request ID, collection size/order, names, types, export flags, outline formats and
all axis coordinates match its immutable snapshot. It prefers an exact saved ID.
When that ID has regenerated, only a unique matching descriptor in the verified
slot can resolve it. ID collisions, ambiguity, incomplete evidence and drift fail.
Unbound workers retain strict exact-ID behavior. No source Save, instance rewrite,
bridge change, protocol change or additional public tool is involved.

`report.instanceResolution` records the method, requested live ID, saved ID and
index. Artifact generation, table/shaping verification and local publication
continue through the existing guarded pipeline.

## Validation

- Focused export/binding tests: 49 passed.
- Full source-checkout Python suite: 3,173 passed, three skipped, five existing
  dependency warnings. This is the 2.3.1/build69 source baseline, not a claim that
  the unrelated in-progress 2.4.0 worktree passed its complete suite.
- Managed package and synchronized skill checks pass; `git diff --check` passes.
- The same 19 binding tests also pass against the constructed 2.4.0 sidecar.
- A normal 2.3.1 build was produced for source validation and was not installed.
  The running 2.4.0/build70 installation has unrelated newer code. All four
  modified existing modules exactly matched their source-checkout baselines.
  Two deterministic copies of that installed sidecar plus only the five changed
  module files have identical official payload fingerprints.
- Live sidecar: `2.4.0+a08ed849364c`, code hash
  `sha256:a08ed849364c3e93eb0ee7e33d65471063a4b81bd7b133608f82ad911243a7a7`.
  The authenticated idle guard and durable installation transaction replaced
  only the sidecar and its installation receipt, retaining a verified backup.
  Startup exceeded the controller's five-second check. The same live installation
  was subsequently verified and its original transaction reconciled as committed;
  there was no second installation or forced stop.
- Native bridge remains `2.4.0+fa3ef2725832`, code hash
  `sha256:fa3ef2725832d2df1a98a0373a87c91399cc28ed7c34829d4589c9e32f913214`,
  same bridge session. Glyphs was not restarted and no font was mutated or saved.

## Real MCP acceptance

LeftyNote format4, Glyphs4.2/build4202, 1,844 source glyphs. Exact live IDs from
`read_entities` successfully select all three static instances:

| Style | Requested live ID | Saved ID | Index | MCP job |
|---|---|---|---:|---|
| Regular | 6ABC6A6B-39AA-4367-99A2-2994013A182D | 28D31CDC-775D-492F-8D0A-AD5C38DCBDD3 | 0 | job_9c5787d4916d41419c86bfa858d47df9 |
| Bold | 38AC4C56-A2A7-42BD-B0B1-CC9014782984 | 2EE299C2-6E21-4343-BBAD-D17129779420 | 1 | job_168bf130c799458ebcc2096e7da93603 |
| Light | BDAB6438-2222-4981-B7A6-33D10C7A1D0A | CF799820-1903-47FC-A038-7C73E6BB353F | 2 | job_cd34bdbe17924f3db5a57e7aced624c0 |

All three report `source-bound-slot`, export OTF/WOFF2, pass table and HarfBuzz
`ss01` off/on checks on `lll` with unaffected control `.`, and are accepted only
into new local private diagnostic directories. Six OTS checks pass. Each font has
1,803 exported glyphs and the expected weight 300/400/700; decompressed CFF, hmtx,
cmap, GSUB, GPOS and GDEF bytes match between containers for each instance.
An initial test correctly rejected `abc` as an unaffected control: ss01 changes
those letters too. A whitespace-only replacement was rejected by request
validation before creating a job. The final control is absent from ss01's rules.

All 1,887 original font-data files are byte-identical, hash
`5b6c21b70d99c3b423e0fe0db0fc63d9d99c6afdc5dd5df73d940b6971237ce7`.
The retained original document remains clean at generation21, not foreground.
All 41 LeftyNote repository tests pass. Private receipts/binaries remain in that
project's ignored `.release-work/typed-export-fix-20261027/` directory.

These are static diagnostic exports with autoHint on and removeOverlap off. They
do not replace LeftyNote's separately qualified release exports or establish
variable-instance acceptance. No app release, source publication or push occurred.

## Merge into the active 2.4.0 source — 2026-10-27

The owner requested merging the fix so future app builds retain it. The active
checkout was clean on main at `582f8551`; the incoming fix is `d346020e`.
The normal two-parent merge applied without conflicts and preserved the existing
2.4.0/build71 work. Export guidance and the managed hinting reference now describe
source-bound identities, and the synchronized 12-skill package includes them.

The merged source passed **3,266 Python tests**, with three skips and five
dependency deprecation warnings. Two independent final payload builds match
exactly, with sidecar code hash
`sha256:ccb6d813e283a7365fcd9bbaece78da10af65b0852a621263faaf4063fa5ff61`.
Managed-package/synchronization and whitespace checks pass. The native desktop
suite passed **312 tests** with no failures. Its exact unsigned 2.4.0/build71
app passed `verify_desktop_app.py`; its packaged sidecar manifest matches those
deterministic builds and contains the source-identical binding module. App hash:
`1fe48fee501ce1c273094219df128667444d3ae90c393a4a97eb01be1cf37ed6`.

The first desktop attempt selected Xcode's Python3.9 and failed before tests at
the payload import. The supported-Python retry used an explicit Python3.14 path
and fresh DerivedData; both logs remain under build/. No installer/runtime
source workaround was introduced. The candidate app was not installed, and
Glyphs was not restarted. The prior live LeftyNote acceptance continues to bind
the installed sidecar `2.4.0+a08ed849364c`; it does not certify every new build71
feature. There was no signing, release publication or push.
