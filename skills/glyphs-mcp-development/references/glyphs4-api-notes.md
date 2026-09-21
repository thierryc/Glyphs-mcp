# Qualified Glyphs 4 API notes

These are project observations from RV01 on **Glyphs 4.1 (4107)** using the
native CLI, not edits to the pinned official SDK or universal compatibility
claims. RV01 evidence is preserved at commit `a833e599` under
`reports/rv01-realistic-20260914`, T10–T12. Use the installed offline helper to
fetch the official IDs below only when their details are needed.

## Export: GSInstance.generate

Official ID: `api-section-237`, SDK revision
`0f5422db727b78cb42abfb386f33ae0b382b0c4d`.
The signature uses lower camel case; its older uppercase-keyword example failed
in the qualified runtime. For an explicitly selected instance and new directory:

```python
from GlyphsApp import TT, PLAIN

result = instance.generate(
    fontPath=str(output_directory), format=TT, autoHint=False,
    removeOverlap=False, useProductionNames=False, containers=[PLAIN],
)
```

Those export options describe the RV01 test, not production defaults. Preserve
the user's export intent. In that trial `result` was `None` although a valid
TTF was written. Inspect any returned error, verify a new output actually exists,
parse the binary and check the requested shaping behavior. A pre-existing file,
truthy return or zero process exit does not prove a successful new export.

The lean v2 `font_export` worker now fixes this to one exact persistent instance
ID and typed OTF/TTF, PLAIN/WOFF/WOFF2 and generation arguments. It accepts only
`None` or `True` as the native result, then independently parses every output,
checks structural tables/container/variable state and optionally shapes bounded
feature-on/off cases. Output stays private until create-only atomic publication.

## Native feature flags

Official ID: `api-section-262` documents `GSFeature.automatic`. In the qualified
native CLI, feature `automatic` and `disabled` getters could be callable.
Read their value before interpreting it:

```python
def native_value(obj, name):
    value = getattr(obj, name)
    return value() if callable(value) else value

automatic = bool(native_value(feature, "automatic"))
disabled = bool(native_value(feature, "disabled"))
```

A bound method's truthiness is not the feature flag. Do not default missing
properties to false; report unavailable evidence. The `disabled` observation is
native qualification and is not assigned an invented official API entry.

## Native compilation: GSFont.compileFeatures

Official ID: `api-section-130`, same pinned SDK revision. RV01 observed native
`(True, None)` and `(False, NSError)` results:

```python
result = font.compileFeatures()
if not isinstance(result, tuple) or len(result) != 2:
    raise RuntimeError(f"Unverified compile result shape: {result!r}")
succeeded, error = result
if not succeeded:
    raise RuntimeError(f"Feature compilation failed: {error}")
```

Do not use `if result`: the failure tuple is also truthy. Preserve the native
diagnostic; RV01's missing-glyph error named the feature and source line.
Unexpected representations need qualified inspection, not an assumed success.

Lean v2 exposes this only as `feature_compile`: saved mode runs in the external
worker, while live mode runs on Glyphs' main thread. Both hash complete persisted
prefix/class/feature state before and after. Compiler state is diagnostic and
ephemeral; a failed compile is `report.success:false`, not an applicable patch.

## Closed native-action selectors and restoration

The v2 closed-catalog qualifier
`scripts/qualify_simple_v2_native_actions.py` ran plugin-free in the exact
**Glyphs 4.1 (4107)** application. Its startup probe qualified all 17 actions,
canonical worker/bridge hashes matched, every fixture produced an observable
state change, and native Undo → Redo → restoration returned the exact hashes.
An `update_metrics` result saved to a new `.glyphspackage` reopened with the
same after hash. The metrics-key proof changed an intentionally wrong RSB from
1 to the referenced glyph's RSB of 45; this confirms `syncMetrics()` behavior,
not generic bearing recalculation. `updateGlyphInfo(False)` retained the glyph
name.

Qualified selectors and fixed arguments:

| Action | Selector / call |
|---|---|
| `update_metrics` | `syncMetrics()` |
| `correct_path_direction` | `correctPathDirection()` |
| `round_coordinates` | `roundCoordinates()` |
| `add_extremes` | `addNodesAtExtremes(force, False)` |
| `cleanup_paths` | `cleanUpPaths()` |
| `remove_overlap` | `removeOverlap(False)` |
| `add_missing_anchors` | `addMissingAnchors()` |
| `align_components` | immediate `doAlignComponents()` |
| `decompose_components` | `decomposeComponents()` |
| `decompose_corners` | `decomposeCorners()` |
| `make_components` | `makeComponents()` |
| `reinterpolate` | `reinterpolate()` |
| `connect_open_paths` | `connectAllOpenPaths()` |
| `swap_foreground_background` | `swapForegroundWithBackground()` |
| `update_glyph_info` | `updateGlyphInfo(False)` |
| `update_features` | `updateFeatures()` |
| `update_automatic_feature_block` | exact automatic/automatable block `update()` |

Layer state used `propertyListValueFormat_error_(3, None)`. Restoration used a
deep native layer copy plus `getCopyOfContentFromLayer_doSelection_`, explicit
metric/scalar restoration and paired background restoration only when the
persisted projection contained it. Glyph-info state combines its layer-free
property list with normalized metadata; restoration retains typed metadata.
Whole-font feature restoration retains original native block objects and their
persistent IDs while restoring copied property-list state and exact order.
Single-block restoration applies the same state in place; `update()` therefore
keeps its exact target ID through Undo, Redo and discard.
Do not generalize these snapshots into a public object protocol or treat this
single-build qualification as universal compatibility; the bridge repeats a
cached startup capability probe in every running build.

## Closed compile/export qualification

`scripts/qualify_simple_v2_compile_export.py` also ran plugin-free in exact
**Glyphs 4.1 (4107)**. On a disposable source, saved `compileFeatures()` returned
success with identical full feature hashes. Typed `GSInstance.generate()`
produced parsed plain TTF, WOFF and WOFF2 from one exact static instance plus a
parsed variable TTF from an exact variable setting. Required tables, container
flavors and `fvar` were verified, a feature-on/off HarfBuzz ligature case changed
as expected, its control remained unchanged, and the source file hash did not
change. WOFF/WOFF2 shaping first decodes the verified web container to sfnt bytes;
passing compressed bytes directly to HarfBuzz does not establish behavior.

## Evidence levels

Source review establishes authored code and flags. Native compilation establishes
compiler acceptance on that host. Actual export establishes a produced binary;
inspect its identity, tables and intended instance. Shaping establishes the
tested behavior for the stated text, features, language, script and direction.
Use feature-on/off pairs and unaffected controls. Keep unavailable levels
explicit; a sampled result is not an exhaustive OpenType or variable-font audit.
