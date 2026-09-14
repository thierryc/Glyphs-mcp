# H6 acceptance specification (before implementation)

Add `kerning.groups.v1` for eight explicitly requested GSGlyph side group/key
properties; do not alter existing metadata defaults. Group names and native
lookup keys remain distinct. Missing group is native null; ungrouped key is the
glyph name. Direction semantics must be documented and natively verified.

Add `kerning.pairs.v1`: one `kerning_pairs` selector with an exact master,
explicit LTR/RTL/vertical direction, limit 1–100 (default 100), optional exact raw
`leftKey`/`rightKey` filters and an opaque continuation. Fields are any nonempty
subset of left, right, value. Each requested side is {key, glyph, kind}; preserve
raw storage key, resolve native IDs individually, distinguish group/glyph/unresolved.
Values contains items, total=null, returned, complete, nextCursor, scanned and
scanLimit. Total stays unavailable even on the last page; complete means the
requested live traversal reached its end. No effective-kerning inference.

Native indexed access only. Cap each page at 256 work units, counting both outer
groups (including empty/filtered ones) and inner entries. Later pages resume
indices without rescanning prior pages. An empty incomplete page is valid;
follow its cursor. No full-table copy, sort, glyph-ID map or retained iterator.
Cursor binds document/master/direction/filters, outer count, existing generation
and dirty signals, and a bounded boundary check. Stale or observed edit => discard
partial results and restart. Pages are live, not an atomic snapshot; silent
same-count edits elsewhere can evade bounded guards. No watcher added.

Reject malformed/foreign cursors, unknown fields, out-of-range limits, missing
masters and unavailable indexed native data explicitly. Keep exact-value reads,
seven tools, five jobs and editing/Undo hooks unchanged. Missing private capability
requires coordinated installation update, with no fallback workflow.

Test three-master fixture, groups and ungrouped glyphs, empty table/groups,
zero/fractions/absence, raw unresolved IDs, all directions, filters, pagination,
right-filter misses exceeding one work page, exact read round trips, stale cursor
on edits/replacement/close, dirty reads without save, object/data preservation.
Independent native oracle and pinned open-source Roboto Slab must agree.

Measure first attempt, warm-up and five repetitions on fresh disposable copies for
small and multi-page synthetic/realistic reads. Record discovery separately, HTTP
and native callback timing, counts, load and o200k_base payload estimates. Never
count missing evidence as pass. Install through existing installer, verify loaded
fingerprints and all configured skill payload hashes. Preserve previous reports.
