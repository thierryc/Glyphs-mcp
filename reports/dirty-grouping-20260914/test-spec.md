# Lean grouping follow-up

Implement only lazy document fallback grouping and one owned native group per
touched glyph. Keep current exact inverse callbacks, operations, cancellation,
discard, seven tools and native APIs. Per the user's clarification, native
Redo→Undo dirty-state parity is acceptable; do not add a workaround or counter
compensation. Discard retains existing reverse-write semantics.

Before installation: small native-manager doubles cover original true/false
automatic grouping, shared glyph managers, actual fallback use, pre-existing
groups, partial setup, cleanup failure and chunked completion/cancellation.
Run the relevant lean suite and native source gate on a three-master/two-glyph
fixture. Verify exact values, object/hint/metadata preservation, first-Undo
change counts, flags, partial-write restoration and busy-group refusal. Run the
existing fractional exact-history native gate. Build twice and require identical
payloads with only the bridge fingerprint changed.

Installed checks use fresh disposable copies of the previous investigation's
fixture and the three-master extension. Verify running identity, initial width
application, native UI Undo/Redo, per-glyph Undo across masters, unrelated edits
and whole-job discard. Compare first-Undo dirty state to the recorded baseline.
Keep native data, dirty flags, HTTP latency and helper timing distinct. This is
a targeted correctness qualification; no full latency benchmark is claimed.

One existing GUI document was already dirty at the start of this follow-up.
Do not implicitly save/discard its edits. The candidate may be installed only
after the user resolves those edits or authorizes a new saved disposable copy.
The existing installer requires Glyphs to be closed. No automatic restart
service or history recovery framework is introduced.

Preserve baseline fixtures, previous reports, configured skills, v1, original
fonts, companions and unrelated worktree changes. Normal autosaving stays at its
original value. Remove the temporary setup/read helper and close only the owned
test fonts. Stop on a new native crash and retain evidence.
