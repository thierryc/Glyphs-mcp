# Master compatibility playbook

Use this playbook after the initial host review for one glyph. The objective is
an evidence-backed repair, not making every drawing interpolate at any cost.

## Diagnostic inventory

Record every interpolation-participating layer and compare it with one explicit
reference master. Do not treat raw indices or absolute coordinates as proof of
correspondence.

For every layer, capture:

- ordered shapes, distinguishing paths from components;
- component glyph names and component order;
- anchor-name set;
- path count and, for each path, open/closed state, contour direction, shape
  order, semantic start landmark, and ordered node types;
- on-curve and off-curve counts, plus the smallest per-path count delta;
- the cyclic node-type sequence for closed paths and the linear sequence for
  open paths.

Compare corresponding paths by semantic position, bounds, extrema/corner class,
neighboring segments, tangents, and curvature. Use node indices only after the
correspondence is established.

## Classification

### Order or phase only

Use this class only when every layer has the same shapes and topology and the
difference is fully explained by shape order, path direction, or a cyclic start
phase. Coordinates must not need to change.

### Nearly compatible

Use this class when shapes correspond unambiguously and the remaining issue is
localized: a small node-count delta, one line/curve type difference, one missing
component with an obvious matching role, or one missing anchor name. “Small” is
evidence, not a fixed numeric threshold: explain the exact delta and why the
neighboring segments establish a unique location.

### Ambiguous or manual

Use this class for different contour semantics, missing or extra paths without
a unique match, competing landmarks, large/distributed topology differences,
component substitutions, open/closed disagreements, or any repair that would
require inventing the design. Do not automate this class.

## Repair order

1. For each corresponding closed-path set, establish the intended semantic
   first node and require one unambiguous shared cyclic phase across all
   participating layers. When generic operations cannot express the rotation,
   stage one minimal fingerprint-bound `execute_python` edit, inspect its
   immutable semantic preview, and apply only that stored patch after approval.
   Never rotate open paths.
2. Re-read before continuing. If compatibility is still false, repair only an
   unambiguous path/shape order or direction mismatch while preserving geometry
   and all node fields.
3. Align component identities and order only when the corresponding component
   role is certain. Never decompose components merely to silence compatibility.
4. Align anchor-name sets with explicit generic operations only when the missing or
   extra semantic anchor is clear. Preserve intentional coordinates unless an
   anchor move was separately requested.
5. For a localized on-curve count difference, insert a point only on the
   corresponding segment and preserve the segment geometry. Re-read the exact
   node sequence and geometry afterward.
6. If compatibility requires a new off-curve node or a line-to-curve conversion
   that introduces handles, stop before editing. Show the glyph, target master,
   path and segment, before/after node-type sequence, proposed handle placement,
   geometry-preservation evidence, and why it is necessary. Continue only after
   explicit permission.
7. Use `preview_change` for an explicit reviewed replacement. If a narrow edit
   is not expressible there, use `execute_python` in `staged_document` mode
   against the exact fingerprint. Inspect the semantic preview and apply the
   stored patch through `apply_change`; do not rerun modified code live.

Stop after any unexpected coordinate, node type, connection, smoothness,
orientation, name, anchor, component, shape-order, or open/closed-state change.

## Guided manual feedback

When automatic repair is unsafe, identify the first unresolved mismatch and
give layer-specific directions rather than generic advice:

- **Start point:** switch to the named layer, right-click the identified
  on-curve landmark, and choose **Make Node First**.
- **Shape order:** use **Filter > Shape Order** and place the named paths or
  components on the same row/order across the listed layers.
- **Path direction:** use **Path > Correct Path Direction** only after noting
  that it may also normalize start nodes and reorder shapes; re-check the result
  instead of treating the command as an oracle.
- **Visual diagnosis:** enable **View > Show Master Compatibility**. Green means
  compatible segments, yellow can indicate an angle/start-point problem, and
  red indicates a missing segment or line/curve mismatch.
- **Nodes:** add or remove the identified node on the corresponding segment;
  preserve the curve and repeat the diagnostic. Obtain permission before any
  off-curve addition.
- **Components or anchors:** make component names/order and anchor-name sets
  match only where the semantic correspondence is intended.

## Completion gate

After each repair batch, re-read all participating layers and the document
fingerprint, rerun the compatibility review, and read the host-derived glyph
property. Success requires `mastersCompatible == true` and no unexpected
changes. If the property remains false, return `unresolved`, list the remaining
mismatches and manual steps, and leave the font unsaved.

Even after success, warn when correspondence lines cross or shapes exchange
roles. The host flag confirms technical structure, not interpolation quality.
