# Lean start-node correspondence

For the seven-tool catalog advertised by `get_status`, use `list_documents` to
select one clean saved font. `start_job(kind="start_nodes", glyphs=[...])`
matches one explicit contour across selected masters, externally.

Options select `masters` (2-32), `path` (one contour index), `referenceMaster`
and an optional `referenceNode` landmark. The default landmark is the reference
contour's current native start. The workflow retains the reference layer's
existing cyclic phase and aligns the other layers to it. A repeat is a no-op.
It rejects ambiguous landmarks, mismatched cyclic types or winding, missing
contours, and open paths. This is supported correspondence, not arbitrary repair.

Inspect `get_job` for the explicit reference, selected landmark in each master
and proposed cyclic shifts. Use `apply_job` to display the native reorder.
`read_entities` can verify explicit layer `outlineHash` values. Preserve the
cyclic geometry, node types, smooth flags, user data and hints; check native
Undo/Redo and use `discard_job` to restore the full job. Save remains the
designer's acceptance action. Do not save an applied design automatically.
