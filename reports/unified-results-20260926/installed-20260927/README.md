# Installed qualification — September 27, 2026

Commit `d75404ec` is installed through the established `install_simple_v2.py`
transaction, using `build/simple-native-scripting` and `--only mcp --start`.
Glyphs 4.1 (4107) was gracefully quit with no documents open and relaunched.
The user had closed Dactylotype; it was never reopened, saved or modified here.

The sidecar (`7729847c3017…`) and bridge (`4ee7d4c936ad…`) initialization-time
fingerprints match the source-verified build and installed files. Twelve tools,
`script.native.v1` and private `edit.prepare.native.v1` are present. Both inspector
plugins, port 9680 and automatic-start settings are unchanged. See
[installation](installation.json), [loaded status](status.json) and the parent
[identity comparison](../identity-files.json).

## Actual editor and installed Codex text workflow

Tests used disposable `.glyphs` and `.glyphspackage` fixtures with seven glyphs,
three masters, named fractional nodes, foregrounds, backgrounds, anchors and
layer metadata. The default native master plus two added masters account for
three masters; exact IDs were used. Fixture creation uses standalone native
serialization. Saves below use the actual running editor.

| Check | Observed result |
|---|---|
| Typed Keep and blocker | Three A widths were changed. Waiting color work identified the original workflow. Keep returned Completed with no Save receipt, ended recovery and removed temporary artifacts. Duplicate Keep returned the same result. Waiting work moved to its dirty-font Save prerequisite. |
| Native Undo/Redo after Keep | Actual editor shortcuts changed A width `501.25 → 500 → 501.25`; fresh MCP reads verified both transitions and untouched B width 500. |
| Dirty prerequisite Save | Save and continue returned one verified native Save receipt with `dirtyAfter=false` before color preparation. Method-level Save calls were not independently instrumented. |
| Four optimized routes | Installed job records report `preparationRoute=native` for width, Dimensions, color and coordinate-only outlines. See [route evidence](preparation-routes.json). Zero-copy/worker assertions belong to the separate paired benchmark; this installed pass did not independently instrument process creation. |
| Color and Dimensions | B read back as red/0; HV read back as 80.25. Save font completed with native-and-source-hash receipts. |
| Fractional typed background edit | A background node `(10.25, 0) → (10.5, -0.5)`; foreground and other nodes/names remained unchanged. Selective Undo restored its exact recorded path hash. |
| Whole script, both formats | A node became `(17.5, -3.5)`; H/n/o advances became 520.75 and their nodes moved right by 12.5; exact A/V and T/o pairs became −60.25 and −45.5. B stayed width 500. These are fixed scripted operations, not optical spacing/collision algorithms. |
| Duplicate Run and optional details | Reusing Run did not repeat geometry changes. Full details returned exact source/parameters and literal markup-looking output. Ordinary polling stayed compact. This is text evidence, not visual HTML rendering. |
| Whole-font restoration | Reload restored paths, widths and absent kerning in both formats. In `.glyphs`, it also replaced a later manual width change to 778; the editor Edit menu then showed Undo and Redo disabled. Both reloads returned fresh clean bindings. |
| Sidecar reconnect | Guarded stop/start changed the sidecar process ID. The completed package script became Interrupted, required Check result, recovered Applied and retained the same node without replay. Restore succeeded and Wait remained disabled. See [reconnect](reconnect.json). |
| Callback and script Keep | One package callback changed A width `500 → 500.5`. Waiting typed work referenced its workflow. Script Keep released that blocker, preserving the dirty prerequisite. |
| Manual save | Editor Save followed by Check and continue prepared B's typed width edit; B read back as 500.25. |
| Save As | New `.glyphs` and `.glyphspackage` destinations completed with `originalSourceUnchanged=true`. No existing destination was overwritten. |
| Intentional partial failure | A callback exception after mutation produced Failed, `partialEditsPossible=true`, no automatic Keep action and Keep/Restore choices. Following work stayed blocked. Restoration supplied a fresh binding; the waiting preview became Ready against it and was discarded without applying. |
| Cleanup | Both saved disposable fonts were closed. No documents or active native operations remained. See [cleanup](cleanup.json). |

[Complete call evidence](conversation-evidence.json) retains intermediate results,
including two rejected color reads with an incorrect selector field. The corrected
`{kind: glyph, id: B}` read passed. No unexplained Run/Keep transition occurred in
these controlled sequences; this does not establish the origin of the earlier
report's unattributed interactions.

## Installed timing observations

Single measured Codex tool calls; these are not five-run distributions or
end-to-end measurements. Preparing/Applying returns exclude later polling.
All measurements exclude model/UI interaction gaps.

| Call | Seconds | Return state |
|---|---:|---|
| Start typed width | 0.168 | Preparing |
| Dirty Save and continue | 3.540 | Preparing; verified save |
| Whole-script Run, `.glyphs` | 3.424 | Applying |
| Whole-script Run, `.glyphspackage` | 4.573 | Applying |
| Restore saved `.glyphs` | 10.153 | Restored; fresh binding |

The longest recorded installed preparation chunk was **0.111 s**, for color.
This exceeds the standalone benchmark's 0.033 s preparation maximum. Editor
overhead and noninterruptible native calls prevent treating the fixture result
as a responsiveness guarantee. The 320-run matrix is unchanged and is not pooled
with these installed observations.

## Remaining qualification limits

- Computer Use rejected access to `com.openai.codex` for safety reasons. No
  alternate automation path was used. Installed text actions, explicit Wait and
  reconnect persistence passed; visible countdown/progress, Details interaction,
  hidden/disconnected-card behavior and visual rendering remain unqualified in
  an installed card host. Existing mock-host tests remain passing evidence.
- Live failed/uncertain-save fault injection, existing-destination rejection,
  cancellation, closed-document and overwritten-baseline sequences, and
  never-saved-document Save As were not repeated on this loaded identity.
  Current automated tests and earlier-candidate reports remain separate evidence.
- The existing unnamed-node null-to-empty normalization remains a separate
  typed-recovery follow-up. Named fixture nodes do not qualify absent metadata.

Installation and the listed editor/text checks passed. The broader milestone is
not unconditionally complete while installed-card qualification is blocked.
No release was published and no installed plugin cache was edited.
