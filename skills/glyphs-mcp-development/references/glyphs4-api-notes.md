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

## Evidence levels

Source review establishes authored code and flags. Native compilation establishes
compiler acceptance on that host. Actual export establishes a produced binary;
inspect its identity, tables and intended instance. Shaping establishes the
tested behavior for the stated text, features, language, script and direction.
Use feature-on/off pairs and unaffected controls. Keep unavailable levels
explicit; a sampled result is not an exhaustive OpenType or variable-font audit.
