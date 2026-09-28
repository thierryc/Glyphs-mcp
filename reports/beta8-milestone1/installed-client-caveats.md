# Installed-client evidence boundaries

- The installed Codex MCP connection completed all 10,000 callbacks in the
  `.glyphs` flip. The callback asserted every transformed path and owning
  foreground control. The wrapper correctly retained `changesVerified=false`:
  these are script assertions, not independent wrapper verification.
- An attempted two-path geometry read was rejected because geometry reads accept
  one selector. The later restoration and cancellation probes used valid single
  selectors. The rejected read is retained in the raw evidence, not counted as
  successful verification.
- A duplicate Run dispatch did not replay the code. Optional full details
  included exact source and output; ordinary polling omitted those fields.
- Both `.glyphs` and `.glyphspackage` obtained a successful actual editor Save
  receipt before the dirty-baseline cancellation run. Cancellation stopped at
  390 and 1,290 callbacks respectively. Restore returned fresh bindings and the
  original fractional path hash. Native source qualification independently
  verifies every fixture target after restoration.
- After some UI interaction, a restored fixture changed from the initially
  reported clean state to dirty, and the next reviewed action was correctly
  rejected as stale. The Edit menu also showed an available Undo item. These
  observations do not establish that restored editor state remains clean or
  that no later UI activity adds Undo state. They were not reproduced in the
  headless fixture. The fixtures deliberately have a second master without
  stored layers. Comparing the original file with the authorized editor Save
  shows that `probe0` gained that second-master layer (width 600) after UI
  interaction. Native editor normalization is therefore a possible explanation,
  not a proven cause of every dirty transition. No recovery code was changed
  in this milestone; this observation remains a follow-up, not a clean-state
  guarantee.
- The package fixture was finally closed with **Don't Save** for that later
  unsaved state; no unrelated document was opened, saved or closed. Final
  installed status reports zero open documents and zero active operations.
- The active-card countdown and rendered card appearance were not exercised in
  this milestone. These tests use installed text actions; previous card-test
  qualification limitations are not superseded.
